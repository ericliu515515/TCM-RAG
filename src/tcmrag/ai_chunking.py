from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from langchain_community.vectorstores import FAISS
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from tcmrag.chunk import extract_pages
from tcmrag.chunk_quality import (
    read_jsonl,
    validate_candidate_chunks,
    write_json,
    write_jsonl,
)
from tcmrag.source_embeddings import (
    EMBEDDING_MODEL_NAME,
    chunks_to_documents,
    evaluate_vectorstore,
)


DEFAULT_CHUNKER_MODEL = "gpt-4o-mini"
DEFAULT_JUDGE_MODEL = "gpt-4o-mini"
DEFAULT_MAX_ATTEMPTS = 7
MIN_ACCEPTED_SEPARATION_SCORE = 0.6
MAX_SAVED_CHUNK_RUNS = 15
PAGES_FILENAME = "pages.json"
RUNNER_TIMEOUT_SECONDS = 45
ALLOWED_IMPORT_ROOTS = {
    "collections",
    "itertools",
    "math",
    "re",
    "statistics",
    "typing",
}
FORBIDDEN_CALL_NAMES = {
    "__import__",
    "compile",
    "delattr",
    "eval",
    "exec",
    "exit",
    "getattr",
    "globals",
    "input",
    "locals",
    "open",
    "quit",
    "setattr",
    "vars",
}
FORBIDDEN_ATTRIBUTE_NAMES = {
    "chmod",
    "mkdir",
    "open",
    "popen",
    "read",
    "remove",
    "rename",
    "rmdir",
    "rmtree",
    "system",
    "unlink",
    "write",
}


class GeneratedCodeSafetyError(ValueError):
    pass


ChunkingProgressCallback = Callable[[dict[str, Any]], None]
ATTEMPT_PROGRESS_STAGES = (
    "generate",
    "validate",
    "evaluate",
    "feedback",
    "complete",
)
ATTEMPT_PROGRESS_STAGE_INDEX = {
    stage: index for index, stage in enumerate(ATTEMPT_PROGRESS_STAGES)
}
FINAL_PROGRESS_STAGES = ("finish",)


def report_chunking_progress(
    progress_callback: ChunkingProgressCallback | None,
    *,
    attempt: int,
    max_attempts: int,
    stage: str,
    message: str,
    feedback: str = "",
    feedback_title: str = "",
    run_id: str = "",
) -> None:
    if progress_callback is None:
        return

    stage_name = str(stage or "").strip()
    attempt_count = max(int(max_attempts or 0), 1)

    if stage_name in ATTEMPT_PROGRESS_STAGE_INDEX:
        stage_index = ATTEMPT_PROGRESS_STAGE_INDEX[stage_name]
        total_steps = (attempt_count * len(ATTEMPT_PROGRESS_STAGES)) + len(FINAL_PROGRESS_STAGES)
        completed_steps = (
            max(int(attempt or 0) - 1, 0) * len(ATTEMPT_PROGRESS_STAGES)
        ) + stage_index + 1
        progress = min(completed_steps / total_steps, 0.99)
    elif stage_name == "finish":
        progress = 1.0
    else:
        progress = 0.0

    try:
        progress_callback(
            {
                "attempt": int(attempt or 0),
                "max_attempts": attempt_count,
                "stage": stage_name,
                "progress": progress,
                "message": message,
                "feedback": str(feedback or ""),
                "feedback_title": str(feedback_title or ""),
                "run_id": str(run_id or ""),
            }
        )
    except Exception:
        return


def run_ai_chunking(
    source: dict,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    progress_callback: ChunkingProgressCallback | None = None,
) -> dict:
    source_dir = Path(source["source_dir"])
    pages_path, pages = load_extracted_pdf_pages(source)
    embedding_model = OpenAIEmbeddings(model=EMBEDDING_MODEL_NAME)

    chunk_runs_dir = source_dir / "chunk_runs"
    chunk_runs_dir.mkdir(parents=True, exist_ok=True)

    text_error = extractable_text_error(pages)
    if text_error:
        run_id = make_run_id(0)
        run_dir = chunk_runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        prune_chunk_runs(chunk_runs_dir)
        validation = {
            "passed": False,
            "errors": [text_error],
            "warnings": [],
            "stats": {
                "page_count": len(pages),
                "non_empty_page_count": count_non_empty_pages(pages),
            },
            "chunks": [],
        }
        write_json(run_dir / "validation.json", validation)
        feedback_for_next_attempt = build_feedback_for_next_attempt(validation, None)
        (run_dir / "feedback.txt").write_text(feedback_for_next_attempt, encoding="utf-8")
        result = build_attempt_result(
            run_id,
            attempt=0,
            max_attempts=0,
            accepted=False,
            candidate_chunks_path=run_dir / "chunks.candidate.jsonl",
            validation=validation,
            judge_report=None,
            retrieval_evaluation=None,
            feedback_for_next_attempt=feedback_for_next_attempt,
        )
        report_chunking_progress(
            progress_callback,
            attempt=0,
            max_attempts=max_attempts,
            stage="finish",
            message="Chunk generation stopped because the PDF has no extractable text.",
            feedback=feedback_for_next_attempt,
            feedback_title="Latest attempt feedback",
            run_id=run_id,
        )
        update_source_manifest(source_dir, "failed", run_id, result)
        return result

    feedback = ""
    last_result = None
    attempt_results = []

    for attempt in range(1, max_attempts + 1):
        run_id = make_run_id(attempt)
        run_dir = chunk_runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        prune_chunk_runs(chunk_runs_dir)

        result = run_chunk_attempt(
            source=source,
            pages=pages,
            pages_path=pages_path,
            run_dir=run_dir,
            attempt=attempt,
            max_attempts=max_attempts,
            feedback=feedback,
            embedding_model=embedding_model,
            progress_callback=progress_callback,
        )
        attempt_results.append(result)
        last_result = result

        feedback = result["feedback_for_next_attempt"]

        if result["accepted"]:
            accepted_result = finalize_successful_attempt(source, result)
            if accepted_result is not None:
                separation_score = retrieval_separation_score(
                    accepted_result.get("retrieval_evaluation")
                )
                report_chunking_progress(
                    progress_callback,
                    attempt=int(accepted_result.get("attempt") or max_attempts),
                    max_attempts=max_attempts,
                    stage="finish",
                    message=(
                        f"Accepted `{accepted_result['run_id']}` because retrieval "
                        f"separation `{format_metric_number(separation_score)}` "
                        f"exceeded `{MIN_ACCEPTED_SEPARATION_SCORE:.1f}`."
                    ),
                    feedback=accepted_result.get("feedback_for_next_attempt") or "",
                    feedback_title="Latest feedback",
                    run_id=accepted_result["run_id"],
                )
                update_source_manifest(source_dir, "accepted", accepted_result["run_id"], accepted_result)
                return accepted_result

    selected_result = select_best_attempt_result(attempt_results)
    if selected_result is not None:
        accepted_result = finalize_successful_attempt(
            source,
            selected_result,
            accepted_reason="highest_separation_score_fallback",
        )
        if accepted_result is not None:
            separation_score = retrieval_separation_score(
                accepted_result.get("retrieval_evaluation")
            )
            report_chunking_progress(
                progress_callback,
                attempt=int(accepted_result.get("attempt") or max_attempts),
                max_attempts=max_attempts,
                stage="finish",
                message=(
                    f"No run exceeded `{MIN_ACCEPTED_SEPARATION_SCORE:.1f}`. "
                    f"Accepted `{accepted_result['run_id']}` with the highest "
                    f"retrieval separation `{format_metric_number(separation_score)}`."
                ),
                feedback=accepted_result.get("feedback_for_next_attempt") or "",
                feedback_title="Best available run feedback",
                run_id=accepted_result["run_id"],
            )
            update_source_manifest(source_dir, "accepted", accepted_result["run_id"], accepted_result)
            return accepted_result

    selected_result = last_result

    report_chunking_progress(
        progress_callback,
        attempt=int(selected_result.get("attempt") or max_attempts) if selected_result else max_attempts,
        max_attempts=max_attempts,
        stage="finish",
        message=(
            "Chunk generation finished without a valid retrieval separation run."
        ),
        feedback=(selected_result.get("feedback_for_next_attempt") or "") if selected_result else "",
        feedback_title="Latest attempt feedback",
        run_id=selected_result["run_id"] if selected_result else "",
    )
    if selected_result is not None:
        update_source_manifest(source_dir, "failed", selected_result["run_id"], selected_result)
        return selected_result

    update_source_manifest(source_dir, "failed", "", None)
    return {}


def extract_pdf_pages_for_source(source: dict) -> dict:
    source_dir = Path(source["source_dir"])
    pdf_path = find_pdf_path(source)
    if pdf_path is None:
        raise FileNotFoundError("No PDF file found for this source.")

    pages = extract_pages(pdf_path)
    pages_path = source_dir / PAGES_FILENAME
    write_json(pages_path, {"pages": pages})

    page_count = len(pages)
    non_empty_page_count = count_non_empty_pages(pages)
    text_error = extractable_text_error(pages)
    result = {
        "status": "failed" if text_error else "extracted",
        "pages_path": PAGES_FILENAME,
        "page_count": page_count,
        "non_empty_page_count": non_empty_page_count,
        "error": text_error,
        "updated_at": now_iso(),
    }
    update_pdf_extraction_manifest(source_dir, result)
    return result


def load_extracted_pdf_pages(source: dict) -> tuple[Path, list[dict[str, Any]]]:
    source_dir = Path(source["source_dir"])
    extraction = source["metadata"].get("pdf_extraction")
    pages_filename = PAGES_FILENAME

    if isinstance(extraction, dict):
        pages_filename = str(extraction.get("pages_path") or PAGES_FILENAME)

    pages_path = source_dir / pages_filename
    if not pages_path.exists():
        raise FileNotFoundError("Extract PDF before generating chunks.")

    try:
        payload = json.loads(pages_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Extracted PDF text file is invalid JSON: {exc}") from exc

    pages = payload.get("pages")
    if not isinstance(pages, list):
        raise ValueError("Extracted PDF text file does not contain a pages list.")

    return pages_path, pages


def run_chunk_attempt(
    source: dict,
    pages: list[dict[str, Any]],
    pages_path: Path,
    run_dir: Path,
    attempt: int,
    max_attempts: int,
    feedback: str,
    embedding_model,
    progress_callback: ChunkingProgressCallback | None = None,
) -> dict:
    run_id = run_dir.name
    report_chunking_progress(
        progress_callback,
        attempt=attempt,
        max_attempts=max_attempts,
        stage="generate",
        message=f"Attempt {attempt}/{max_attempts}: generating chunker script.",
        feedback=feedback,
        feedback_title="Previous attempt feedback" if feedback else "",
        run_id=run_id,
    )
    chunker_code = generate_chunker_script(source, pages, attempt, feedback)
    chunker_path = run_dir / "chunker.py"
    chunker_path.write_text(chunker_code, encoding="utf-8")

    raw_chunks_path = run_dir / "chunks.raw.jsonl"
    candidate_chunks_path = run_dir / "chunks.candidate.jsonl"
    validation_path = run_dir / "validation.json"
    judge_report_path = run_dir / "judge_report.json"
    retrieval_evaluation_path = run_dir / "retrieval_evaluation.json"
    feedback_path = run_dir / "feedback.txt"

    try:
        report_chunking_progress(
            progress_callback,
            attempt=attempt,
            max_attempts=max_attempts,
            stage="validate",
            message=f"Attempt {attempt}/{max_attempts}: validating generated chunker.",
            run_id=run_id,
        )
        validate_generated_chunker_code(chunker_code)
    except GeneratedCodeSafetyError as exc:
        validation = {
            "passed": False,
            "errors": [str(exc)],
            "warnings": [],
            "stats": {},
            "chunks": [],
        }
        feedback_for_next_attempt = build_feedback_for_next_attempt(validation, None)
        write_json(validation_path, validation)
        feedback_path.write_text(feedback_for_next_attempt, encoding="utf-8")
        report_chunking_progress(
            progress_callback,
            attempt=attempt,
            max_attempts=max_attempts,
            stage="complete",
            message=f"Attempt {attempt}/{max_attempts} complete: generated code failed safety validation.",
            feedback=feedback_for_next_attempt,
            feedback_title="Latest attempt feedback",
            run_id=run_id,
        )
        return build_attempt_result(
            run_id,
            attempt=attempt,
            max_attempts=max_attempts,
            accepted=False,
            candidate_chunks_path=candidate_chunks_path,
            validation=validation,
            judge_report=None,
            retrieval_evaluation=None,
            feedback_for_next_attempt=feedback_for_next_attempt,
        )

    runner_result = run_generated_chunker(
        chunker_path=chunker_path,
        pages_path=pages_path,
        raw_chunks_path=raw_chunks_path,
        run_dir=run_dir,
    )
    if not runner_result["ok"]:
        validation = {
            "passed": False,
            "errors": [runner_result["error"]],
            "warnings": [],
            "stats": {},
            "chunks": [],
        }
        feedback_for_next_attempt = build_feedback_for_next_attempt(validation, None)
        write_json(validation_path, validation)
        feedback_path.write_text(feedback_for_next_attempt, encoding="utf-8")
        report_chunking_progress(
            progress_callback,
            attempt=attempt,
            max_attempts=max_attempts,
            stage="complete",
            message=f"Attempt {attempt}/{max_attempts} complete: generated chunker failed to run.",
            feedback=feedback_for_next_attempt,
            feedback_title="Latest attempt feedback",
            run_id=run_id,
        )
        return build_attempt_result(
            run_id,
            attempt=attempt,
            max_attempts=max_attempts,
            accepted=False,
            candidate_chunks_path=candidate_chunks_path,
            validation=validation,
            judge_report=None,
            retrieval_evaluation=None,
            feedback_for_next_attempt=feedback_for_next_attempt,
        )

    report_chunking_progress(
        progress_callback,
        attempt=attempt,
        max_attempts=max_attempts,
        stage="validate",
        message=f"Attempt {attempt}/{max_attempts}: validating candidate chunks.",
        run_id=run_id,
    )

    try:
        raw_chunks = read_jsonl(raw_chunks_path)
    except ValueError as exc:
        validation = {
            "passed": False,
            "errors": [str(exc)],
            "warnings": [],
            "stats": {},
            "chunks": [],
        }
    else:
        validation = validate_candidate_chunks(
            raw_chunks=raw_chunks,
            pages=pages,
            source_id=source["id"],
            display_name=source["display_name"],
            source_url=source_url_for_source(source),
        )
        write_jsonl(candidate_chunks_path, validation["chunks"])

    write_json(validation_path, {key: value for key, value in validation.items() if key != "chunks"})

    retrieval_evaluation = None
    if validation["passed"]:
        report_chunking_progress(
            progress_callback,
            attempt=attempt,
            max_attempts=max_attempts,
            stage="evaluate",
            message=f"Attempt {attempt}/{max_attempts}: evaluating retrieval separation.",
            run_id=run_id,
        )
        retrieval_evaluation = evaluate_candidate_chunks(
            source=source,
            chunks=validation["chunks"],
            embedding_model=embedding_model,
        )
        write_json(retrieval_evaluation_path, retrieval_evaluation)
    else:
        report_chunking_progress(
            progress_callback,
            attempt=attempt,
            max_attempts=max_attempts,
            stage="evaluate",
            message=(
                f"Attempt {attempt}/{max_attempts}: skipping retrieval evaluation "
                "because validation failed."
            ),
            run_id=run_id,
        )

    accepted = (
        validation["passed"]
        and separation_score_passed(retrieval_evaluation)
    )
    separation_score = retrieval_separation_score(retrieval_evaluation)
    if accepted:
        feedback_for_next_attempt = build_feedback_for_next_attempt(
            validation,
            None,
            retrieval_evaluation,
        )
        feedback_path.write_text(feedback_for_next_attempt, encoding="utf-8")
        report_chunking_progress(
            progress_callback,
            attempt=attempt,
            max_attempts=max_attempts,
            stage="complete",
            message=(
                f"Attempt {attempt}/{max_attempts} complete: "
                f"retrieval separation `{format_metric_number(separation_score)}` passed."
            ),
            feedback=feedback_for_next_attempt,
            feedback_title="Retrieval evaluation",
            run_id=run_id,
        )

        return build_attempt_result(
            run_id,
            attempt=attempt,
            max_attempts=max_attempts,
            accepted=True,
            candidate_chunks_path=candidate_chunks_path,
            validation=validation,
            judge_report=None,
            retrieval_evaluation=retrieval_evaluation,
            feedback_for_next_attempt=feedback_for_next_attempt,
        )

    report_chunking_progress(
        progress_callback,
        attempt=attempt,
        max_attempts=max_attempts,
        stage="feedback",
        message=f"Attempt {attempt}/{max_attempts}: getting chunker feedback.",
        run_id=run_id,
    )
    judge_report = get_chunker_feedback(source, validation, retrieval_evaluation)
    write_json(judge_report_path, judge_report)

    feedback_for_next_attempt = build_feedback_for_next_attempt(
        validation,
        judge_report,
        retrieval_evaluation,
    )
    feedback_path.write_text(feedback_for_next_attempt, encoding="utf-8")
    report_chunking_progress(
        progress_callback,
        attempt=attempt,
        max_attempts=max_attempts,
        stage="complete",
        message=(
            f"Attempt {attempt}/{max_attempts} complete: "
            f"retrieval separation `{format_metric_number(separation_score)}` "
            f"{'passed' if accepted else 'did not pass'}."
        ),
        feedback=feedback_for_next_attempt,
        feedback_title="Latest feedback",
        run_id=run_id,
    )

    return build_attempt_result(
        run_id,
        attempt=attempt,
        max_attempts=max_attempts,
        accepted=accepted,
        candidate_chunks_path=candidate_chunks_path,
        validation=validation,
        judge_report=judge_report,
        retrieval_evaluation=retrieval_evaluation,
        feedback_for_next_attempt=feedback_for_next_attempt,
    )


def generate_chunker_script(
    source: dict,
    pages: list[dict[str, Any]],
    attempt: int,
    feedback: str,
) -> str:
    model_name = os.getenv("OPENAI_CHUNKER_MODEL", DEFAULT_CHUNKER_MODEL)
    llm = ChatOpenAI(model=model_name, temperature=0)
    sample_pages = compact_page_samples(pages)
    repeated_noise_candidates = repeated_page_noise_candidates(pages)

    response = llm.invoke([
        (
            "system",
            "You write safe Python chunking functions for PDF text extracted page by page. "
            "You must optimize for paragraph-sized chunks, removal of repeated page noise, "
            "and near-complete coverage of substantive source text. "
            "Return only Python code. Do not explain.",
        ),
        (
            "user",
            json.dumps(
                {
                    "task": "Write a Python function named chunk_pages(pages).",
                    "input_schema": {
                        "pages": [
                            {"pdf_page": "int", "text": "str"},
                        ]
                    },
                    "output_schema": {
                        "chunks": [
                            {"text": "str", "pdf_pages": ["int"]},
                        ]
                    },
                    "rules": [
                        "Preserve source wording. Do not summarize or translate.",
                        "Keep each chunk coherent for RAG retrieval.",
                        "Paragraph integrity is more important than hitting a target size.",
                        "Prefer section headings and complete concepts as boundaries.",
                        "Every chunk must include the source PDF pages.",
                        "Define chunk_pages only. No file I/O. No network. No subprocess.",
                        "Allowed imports: re, math, statistics, collections, itertools, typing.",
                    ],
                    "hard_requirements": [
                        "Each chunk should contain no more than one paragraph.",
                        "Exception: a very short heading may stay attached to its immediately following paragraph.",
                        "Never cut a paragraph in the middle of a sentence, phrase, or thought.",
                        "If one page has multiple paragraphs, output multiple chunks.",
                        "Do not merge unrelated neighboring paragraphs just to make a larger chunk.",
                        "Short chunks are allowed when the source really contains a short standalone unit, but no more than 10% of chunks should be shorter than 10 chars.",
                        "Do not output empty chunks.",
                        "Do not output heading-only chunks unless the page truly contains only that heading.",
                        "Remove repeated header, footer, watermark, page-number, website-banner, and scan-noise lines before chunking.",
                        "If a line recurs across many pages and looks like page noise, remove it rather than keeping it in chunk text.",
                        "Use repeated_noise_candidates as hints, not blind deletion rules. Do not remove a repeated line if it is substantive content.",
                        "Preserve almost all substantive source text. Only repeated page noise may be discarded.",
                    ],
                    "common_failure_modes_to_avoid": [
                        "Repeated header/footer noise in multiple chunks.",
                        "Chunks that are too large and contain multiple unrelated or loosely related paragraphs.",
                        "Chunk boundaries that cut through paragraphs or leave the next chunk starting mid-thought.",
                        "Coverage collapse where only a tiny fraction of the extracted source text becomes chunks.",
                        "Empty chunks.",
                    ],
                    "priority_order": [
                        "1. Remove repeated page noise.",
                        "2. Split by paragraph boundaries.",
                        "3. Keep a short heading with the paragraph immediately after it.",
                        "4. Preserve substantive source text coverage.",
                        "5. Only then consider chunk size preferences.",
                    ],
                    "recommended_algorithm": [
                        "Normalize line endings and trim whitespace.",
                        "Detect and remove repeated noise lines before paragraph grouping.",
                        "Split page text into paragraph-like blocks.",
                        "Merge a very short heading with the immediately following paragraph.",
                        "Emit one chunk per paragraph-like block after cleanup.",
                        "Discard empty or noise-only blocks.",
                        "When a paragraph continues across consecutive pages, keep it as one coherent chunk with all relevant pdf_pages.",
                    ],
                    "source": {
                        "id": source["id"],
                        "display_name": source["display_name"],
                    },
                    "attempt": attempt,
                    "previous_feedback": feedback,
                    "repeated_noise_candidates": repeated_noise_candidates,
                    "sample_pages": sample_pages,
                },
                ensure_ascii=False,
                indent=2,
            ),
        ),
    ])

    return extract_python_code(str(response.content))


def get_chunker_feedback(
    source: dict,
    validation: dict,
    retrieval_evaluation: dict | None,
) -> dict:
    model_name = os.getenv("OPENAI_CHUNK_JUDGE_MODEL", DEFAULT_JUDGE_MODEL)
    llm = ChatOpenAI(model=model_name, temperature=0)
    chunks = validation.get("chunks", [])
    sample_chunks = build_chunk_samples(chunks)

    response = llm.invoke([
        (
            "system",
            "You provide feedback on chunk quality for a RAG system. "
            "Think carefully, but return only the requested JSON object. "
            "Focus especially on paragraph boundaries, chunk size discipline, and repeated watermark or header noise. "
            "Do not decide pass or fail; retrieval_evaluation.separation_score is the acceptance gate. "
            "Do not reveal hidden chain-of-thought; put a concise rationale in reasoning_summary.",
        ),
        (
            "user",
            json.dumps(
                {
                    "source": {
                        "id": source["id"],
                        "display_name": source["display_name"],
                    },
                    "validation": {
                        "passed": validation["passed"],
                        "errors": validation["errors"],
                        "warnings": validation["warnings"][:20],
                        "stats": validation["stats"],
                    },
                    "retrieval_evaluation": retrieval_evaluation,
                    "sample_chunks": sample_chunks,
                    "required_json_schema": {
                        "reasoning_summary": "string",
                        "problems": ["string"],
                        "feedback_for_chunker": "string",
                    },
                    "feedback_rules": [
                        "Good chunks preserve exact source meaning.",
                        "Good chunks are coherent retrieval units.",
                        "Good chunks should usually map to one paragraph, one definition, one explanation step, or one tightly connected short group of paragraphs.",
                        "Paragraphing into smaller chunks is very important for retrieval quality.",
                        "Short chunks are allowed, but flag it if more than 10% of chunks are shorter than 10 chars unless the source genuinely consists of many short standalone units.",
                        "Flag chunks that are too large and bundle many unrelated or loosely related paragraphs together.",
                        "Flag chunks that cut a paragraph, definition, or explanation in the middle so the next chunk starts mid-thought or mid-phrase.",
                        "Good chunks should keep a short heading with its immediately following body paragraph instead of separating them awkwardly.",
                        "Good chunks should not merge unrelated topics.",
                        "Look closely for repeated watermark, header, footer, scan noise, or site-banner text that should have been removed before chunking.",
                        "Flag watermark or repeated page-noise text that appears in multiple chunks or pollutes the retrieval text.",
                        "Good chunks should transform most of the extracted PDF text into chunks.",
                        "Use validation.stats.source_text_chars, chunk_text_chars, referenced_page_count, source_non_empty_page_count, referenced_source_chars_ratio, chunk_to_source_chars_ratio, short_chunk_count, and short_chunk_ratio to assess coverage and chunk quality.",
                        "Flag substantial extracted text that is missing from chunks without a clear reason.",
                        "Explain validation errors if they exist.",
                        "If retrieval_evaluation is present, use it as an important signal.",
                        "A better chunking run should make bad_avg_top_k_distance meaningfully larger than good_avg_top_k_distance.",
                        "retrieval_evaluation.separation_score = bad_avg_top_k_distance - good_avg_top_k_distance; larger is better.",
                        f"The code stops early when separation_score is greater than {MIN_ACCEPTED_SEPARATION_SCORE:.1f}.",
                        "If no attempt exceeds that target, the code accepts the valid run with the highest separation_score after all attempts.",
                        "If the separation score is weak, explain how the chunk boundaries may be hurting retrieval quality.",
                    ],
                    "review_focus": [
                        "Inspect paragraph boundaries carefully.",
                        "Inspect whether chunks are small enough to be useful retrieval units.",
                        "Inspect whether repeated watermark or header/footer noise remains in chunk text.",
                        "Inspect whether the retrieval separation score suggests the chunking is helping distinguish relevant from irrelevant questions.",
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
        ),
    ])

    try:
        report = extract_json_object(str(response.content))
    except ValueError as exc:
        return {
            "reasoning_summary": "The feedback response could not be parsed as valid JSON.",
            "problems": [f"Feedback model returned invalid JSON: {exc}"],
            "feedback_for_chunker": "Return valid JSON and improve chunk boundaries.",
        }

    return normalize_feedback_report(report)


def validate_generated_chunker_code(code: str) -> None:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise GeneratedCodeSafetyError(f"Generated code has a syntax error: {exc}") from exc

    function_names = {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    if "chunk_pages" not in function_names:
        raise GeneratedCodeSafetyError("Generated code must define chunk_pages(pages).")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_name = alias.name.split(".", 1)[0]
                if root_name not in ALLOWED_IMPORT_ROOTS:
                    raise GeneratedCodeSafetyError(f"Import not allowed: {alias.name}")

        if isinstance(node, ast.ImportFrom):
            root_name = str(node.module or "").split(".", 1)[0]
            if root_name not in ALLOWED_IMPORT_ROOTS:
                raise GeneratedCodeSafetyError(f"Import not allowed: {node.module}")

        if isinstance(node, ast.Call):
            call_name = call_name_from_node(node.func)
            if call_name in FORBIDDEN_CALL_NAMES:
                raise GeneratedCodeSafetyError(f"Call not allowed: {call_name}")

        if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ATTRIBUTE_NAMES:
            raise GeneratedCodeSafetyError(f"Attribute not allowed: {node.attr}")


def run_generated_chunker(
    chunker_path: Path,
    pages_path: Path,
    raw_chunks_path: Path,
    run_dir: Path,
) -> dict:
    runner_path = run_dir / "_run_chunker.py"
    runner_path.write_text(generated_chunker_runner_code(chunker_path), encoding="utf-8")

    try:
        result = subprocess.run(
            [sys.executable, "-I", str(runner_path), str(pages_path), str(raw_chunks_path)],
            cwd=run_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=RUNNER_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "error": f"Generated chunker timed out after {exc.timeout} seconds.",
        }

    if result.returncode != 0:
        return {
            "ok": False,
            "error": (
                f"Generated chunker failed with exit code {result.returncode}.\n"
                f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            ),
        }

    if not raw_chunks_path.exists():
        return {"ok": False, "error": "Generated chunker did not write chunks."}

    return {"ok": True, "error": ""}


def generated_chunker_runner_code(chunker_path: Path) -> str:
    return f"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

chunker_path = Path({str(chunker_path)!r})
pages_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])

spec = importlib.util.spec_from_file_location("generated_chunker", chunker_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

pages = json.loads(pages_path.read_text(encoding="utf-8"))["pages"]
chunks = module.chunk_pages(pages)

if isinstance(chunks, dict) and isinstance(chunks.get("chunks"), list):
    chunks = chunks["chunks"]

if not isinstance(chunks, list):
    raise TypeError("chunk_pages must return a list, or a dict with a list under the 'chunks' key.")

with output_path.open("w", encoding="utf-8") as file:
    for chunk in chunks:
        if not isinstance(chunk, dict):
            raise TypeError("Every chunk must be a dict.")
        file.write(json.dumps(chunk, ensure_ascii=False) + "\\n")
"""


def build_attempt_result(
    run_id: str,
    attempt: int,
    max_attempts: int,
    accepted: bool,
    candidate_chunks_path: Path,
    validation: dict,
    judge_report: dict | None,
    retrieval_evaluation: dict | None,
    feedback_for_next_attempt: str,
    forced_acceptance: bool = False,
    accepted_reason: str | None = None,
) -> dict:
    return {
        "run_id": run_id,
        "attempt": attempt,
        "max_attempts": max_attempts,
        "accepted": accepted,
        "forced_acceptance": forced_acceptance,
        "accepted_reason": accepted_reason,
        "candidate_chunks_path": str(candidate_chunks_path),
        "validation": {
            key: value for key, value in validation.items() if key != "chunks"
        },
        "judge_report": judge_report,
        "retrieval_evaluation": retrieval_evaluation,
        "feedback_for_next_attempt": feedback_for_next_attempt,
    }


def build_feedback_for_next_attempt(
    validation: dict,
    judge_report: dict | None,
    retrieval_evaluation: dict | None = None,
) -> str:
    feedback_blocks = []

    if validation.get("errors"):
        feedback_blocks.append("Validation errors:\n" + "\n".join(validation["errors"]))

    if validation.get("warnings"):
        feedback_blocks.append(
            "Validation warnings:\n" + "\n".join(validation["warnings"][:20])
        )

    if judge_report:
        problems = judge_report.get("problems") or []
        judge_reasoning = str(judge_report.get("reasoning_summary") or "")
        judge_feedback = str(judge_report.get("feedback_for_chunker") or "")
        if problems:
            feedback_blocks.append("Feedback problems:\n" + "\n".join(problems))
        if judge_reasoning:
            feedback_blocks.append("Feedback reasoning summary:\n" + judge_reasoning)
        if judge_feedback:
            feedback_blocks.append("Chunker feedback:\n" + judge_feedback)

    if retrieval_evaluation:
        good_avg = retrieval_evaluation.get("good_avg_top_k_distance")
        bad_avg = retrieval_evaluation.get("bad_avg_top_k_distance")
        separation_score = retrieval_evaluation.get("separation_score")
        feedback_blocks.append(
            "Retrieval separation:\n"
            f"good_avg_top_k_distance={format_metric_number(good_avg)}\n"
            f"bad_avg_top_k_distance={format_metric_number(bad_avg)}\n"
            f"separation_score={format_metric_number(separation_score)}"
        )

    if not feedback_blocks:
        return "Improve chunk coherence and preserve exact source wording."

    return "\n\n".join(feedback_blocks)


def finalize_successful_attempt(
    source: dict,
    result: dict | None,
    accepted_reason: str = "separation_score_threshold",
) -> dict | None:
    if not result:
        return None

    candidate_chunks_path_value = result.get("candidate_chunks_path")
    if not candidate_chunks_path_value:
        return None

    candidate_chunks_path = Path(str(candidate_chunks_path_value))
    if not candidate_chunks_path.exists():
        return None

    try:
        candidate_chunks = read_jsonl(candidate_chunks_path)
    except ValueError:
        return None

    if not candidate_chunks:
        return None

    accepted_path = Path(source["chunks_path"])
    shutil.copyfile(candidate_chunks_path, accepted_path)

    finalized_result = dict(result)
    finalized_result["accepted"] = True
    finalized_result["forced_acceptance"] = False
    finalized_result["accepted_reason"] = accepted_reason
    return finalized_result


def select_best_attempt_result(results: list[dict]) -> dict | None:
    if not results:
        return None

    validated_results = [
        result
        for result in results
        if result.get("validation", {}).get("passed")
        and retrieval_separation_score(result.get("retrieval_evaluation")) is not None
    ]
    if validated_results:
        return max(validated_results, key=attempt_selection_key)

    return None


def attempt_selection_key(result: dict) -> tuple[float, float, float, int]:
    retrieval_evaluation = result.get("retrieval_evaluation") or {}
    separation_score = retrieval_separation_score(retrieval_evaluation)
    bad_avg = metric_number_or_default(
        retrieval_evaluation.get("bad_avg_top_k_distance"),
        default=float("-inf"),
    )
    good_avg = metric_number_or_default(
        retrieval_evaluation.get("good_avg_top_k_distance"),
        default=float("inf"),
    )
    attempt = int(result.get("attempt") or 0)
    return (
        metric_number_or_default(separation_score, default=float("-inf")),
        bad_avg,
        -good_avg,
        -attempt,
    )


def evaluate_candidate_chunks(
    source: dict,
    chunks: list[dict[str, Any]],
    embedding_model,
) -> dict:
    documents = chunks_to_documents(chunks, source)
    vectorstore = FAISS.from_documents(documents, embedding_model)
    evaluation = evaluate_vectorstore(vectorstore)
    evaluation["separation_score"] = retrieval_separation_score(evaluation)
    return evaluation


def retrieval_separation_score(evaluation: dict | None) -> float | None:
    if not isinstance(evaluation, dict):
        return None

    good_avg = metric_number_or_default(evaluation.get("good_avg_top_k_distance"))
    bad_avg = metric_number_or_default(evaluation.get("bad_avg_top_k_distance"))
    if good_avg is None or bad_avg is None:
        return None

    return round(bad_avg - good_avg, 6)


def separation_score_passed(evaluation: dict | None) -> bool:
    separation_score = retrieval_separation_score(evaluation)
    return (
        separation_score is not None
        and separation_score > MIN_ACCEPTED_SEPARATION_SCORE
    )


def metric_number_or_default(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def format_metric_number(value) -> str:
    number = metric_number_or_default(value)
    if number is None:
        return "unknown"
    return f"{number:.6f}"


def prune_chunk_runs(chunk_runs_dir: Path, keep: int = MAX_SAVED_CHUNK_RUNS) -> None:
    run_dirs = sorted(
        path
        for path in chunk_runs_dir.iterdir()
        if path.is_dir()
    )
    excess_count = len(run_dirs) - keep
    if excess_count <= 0:
        return

    for run_dir in run_dirs[:excess_count]:
        shutil.rmtree(run_dir)


def update_source_manifest(
    source_dir: Path,
    status: str,
    run_id: str,
    result: dict | None,
) -> None:
    manifest_path = source_dir / "source.json"
    metadata = json.loads(manifest_path.read_text(encoding="utf-8"))
    metadata["chunks_path"] = "chunks.jsonl"
    metadata["chunking"] = {
        "status": status,
        "latest_run_id": run_id,
        "attempt": result.get("attempt") if result else None,
        "max_attempts": result.get("max_attempts") if result else None,
        "updated_at": now_iso(),
        "forced_acceptance": result.get("forced_acceptance") if result else None,
        "accepted_reason": result.get("accepted_reason") if result else None,
        "judge_report": result.get("judge_report") if result else None,
        "retrieval_evaluation": result.get("retrieval_evaluation") if result else None,
        "validation": result.get("validation") if result else None,
    }
    manifest_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def update_pdf_extraction_manifest(source_dir: Path, result: dict) -> None:
    manifest_path = source_dir / "source.json"
    metadata = json.loads(manifest_path.read_text(encoding="utf-8"))
    metadata["pdf_extraction"] = result
    manifest_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def source_url_for_source(source: dict) -> str:
    return f"source://{source['id']}"


def extractable_text_error(pages: list[dict[str, Any]]) -> str:
    if not pages:
        return "No pages were extracted from this PDF."

    non_empty_page_count = count_non_empty_pages(pages)
    if non_empty_page_count == 0:
        return (
            "This PDF does not contain extractable text. Only text-based PDFs "
            "can be added to RAG."
        )

    return ""


def count_non_empty_pages(pages: list[dict[str, Any]]) -> int:
    return sum(1 for page in pages if str(page.get("text") or "").strip())


def find_pdf_path(source: dict) -> Path | None:
    source_dir = Path(source["source_dir"])
    filenames = []
    original_filename = str(source["metadata"].get("original_filename") or "")

    if original_filename:
        filenames.append(original_filename)

    filenames.extend(source.get("document_files") or [])

    for filename in filenames:
        path = source_dir / filename
        if path.exists() and path.suffix.lower() == ".pdf":
            return path

    for path in sorted(source_dir.glob("*.pdf")):
        return path

    return None


def compact_page_samples(pages: list[dict[str, Any]], max_pages: int = 8) -> list[dict]:
    if not pages:
        return []

    samples = []
    sample_count = min(max_pages, len(pages))
    selected_pages = [pages[index] for index in evenly_spaced_indexes(len(pages), sample_count)]

    for page in selected_pages:
        text = str(page.get("text") or "")
        samples.append({
            "pdf_page": page.get("pdf_page"),
            "text_sample": text[:1200],
        })

    return samples


def repeated_page_noise_candidates(
    pages: list[dict[str, Any]],
    min_page_hits: int = 3,
    max_candidates: int = 20,
) -> list[dict[str, Any]]:
    line_page_counts: Counter[str] = Counter()

    for page in pages:
        page_lines = set()
        for raw_line in str(page.get("text") or "").splitlines():
            normalized = normalize_noise_candidate_line(raw_line)
            if not normalized:
                continue
            page_lines.add(normalized)

        for line in page_lines:
            line_page_counts[line] += 1

    candidates = []
    for line, page_hits in line_page_counts.items():
        if page_hits < min_page_hits:
            continue
        if not looks_like_repeated_page_noise(line, page_hits):
            continue

        candidates.append({
            "text": line,
            "page_hits": page_hits,
        })

    candidates.sort(key=lambda item: (-int(item["page_hits"]), len(str(item["text"]))))
    return candidates[:max_candidates]


def normalize_noise_candidate_line(text: str) -> str:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    return normalized[:120]


def looks_like_repeated_page_noise(text: str, page_hits: int) -> bool:
    if not text:
        return False

    if re.fullmatch(r"[0-9０-９]+[.)、．]?", text):
        return False

    if contains_watermark_like_text(text):
        return True

    if page_hits >= 5 and len(text) <= 40:
        return True

    if re.fullmatch(r"[0-9０-９\-\s_/]+", text):
        return True

    if "http" in text.lower() or ".org" in text.lower() or ".com" in text.lower():
        return True

    if re.search(r"第\s*[0-9一二三四五六七八九十百千]+\s*頁", text):
        return True

    return False


def build_chunk_samples(chunks: list[dict], max_chunks: int = 10) -> list[dict]:
    if len(chunks) <= max_chunks:
        selected = list(chunks)
    else:
        selected = []
        sample_indexes = evenly_spaced_indexes(len(chunks), max_chunks - 3)
        for index in sample_indexes:
            selected.append(chunks[index])

        longest_chunks = sorted(
            chunks,
            key=lambda chunk: len(str(chunk.get("text") or "")),
            reverse=True,
        )[:3]
        selected.extend(longest_chunks)

    deduped = []
    seen_chunk_ids = set()
    for chunk in selected:
        chunk_id = str(chunk.get("chunk_id") or "")
        if chunk_id in seen_chunk_ids:
            continue
        seen_chunk_ids.add(chunk_id)
        deduped.append(chunk)

    return [
        {
            "chunk_id": chunk.get("chunk_id"),
            "pdf_pages": chunk.get("pdf_pages"),
            "chars": len(str(chunk.get("text") or "")),
            "paragraph_count_estimate": estimate_paragraph_count(str(chunk.get("text") or "")),
            "contains_watermark_like_text": contains_watermark_like_text(
                str(chunk.get("text") or "")
            ),
            "text_sample": str(chunk.get("text") or "")[:1800],
        }
        for chunk in deduped
    ]


def evenly_spaced_indexes(total_count: int, sample_count: int) -> list[int]:
    if total_count <= 0 or sample_count <= 0:
        return []

    if sample_count >= total_count:
        return list(range(total_count))

    indexes = []
    for i in range(sample_count):
        index = round(i * (total_count - 1) / max(sample_count - 1, 1))
        if index not in indexes:
            indexes.append(index)

    return indexes


def estimate_paragraph_count(text: str) -> int:
    stripped = text.strip()
    if not stripped:
        return 0

    parts = [part for part in re.split(r"\n\s*\n|(?<=。)\n|(?<=：)\n", stripped) if part.strip()]
    return len(parts)


def contains_watermark_like_text(text: str) -> bool:
    lowered = text.lower()
    return (
        "cnzyy.org" in lowered
        or "仅供学习和查询" in text
        or "请购买正版支持本书作者" in text
        or "琅嬛福地" in text
    )


def extract_python_code(text: str) -> str:
    match = re.search(r"```(?:python)?\s*(.*?)```", text, flags=re.DOTALL)
    if match:
        return match.group(1).strip()

    return text.strip()


def extract_json_object(text: str) -> dict:
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("No JSON object found.")

    value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("Feedback output is not a JSON object.")

    return value


def normalize_feedback_report(report: dict) -> dict:
    problems = report.get("problems") or []
    if not isinstance(problems, list):
        problems = [str(problems)]

    return {
        "reasoning_summary": str(
            report.get("reasoning_summary")
            or report.get("rationale")
            or ""
        ),
        "problems": [str(problem) for problem in problems],
        "feedback_for_chunker": str(report.get("feedback_for_chunker") or ""),
    }


def call_name_from_node(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def make_run_id(attempt: int) -> str:
    return f"run_{now_iso().replace(':', '').replace('-', '')}_{attempt}_{uuid.uuid4().hex[:8]}"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
