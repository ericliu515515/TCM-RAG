from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_openai import ChatOpenAI

from tcmagent.chunk import extract_pages
from tcmagent.chunk_quality import (
    read_jsonl,
    validate_candidate_chunks,
    write_json,
    write_jsonl,
)


DEFAULT_CHUNKER_MODEL = "gpt-4o-mini"
DEFAULT_JUDGE_MODEL = "gpt-4o-mini"
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_JUDGE_SCORE_THRESHOLD = 85
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


def run_ai_chunking(
    source: dict,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    judge_score_threshold: int = DEFAULT_JUDGE_SCORE_THRESHOLD,
) -> dict:
    source_dir = Path(source["source_dir"])
    pdf_path = find_pdf_path(source)
    if pdf_path is None:
        raise FileNotFoundError("No PDF file found for this source.")

    pages = extract_pages(pdf_path)
    pages_path = source_dir / "pages.json"
    write_json(pages_path, {"pages": pages})

    chunk_runs_dir = source_dir / "chunk_runs"
    chunk_runs_dir.mkdir(parents=True, exist_ok=True)

    feedback = ""
    last_result = None

    for attempt in range(1, max_attempts + 1):
        run_id = make_run_id(attempt)
        run_dir = chunk_runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=False)

        result = run_chunk_attempt(
            source=source,
            pages=pages,
            pages_path=pages_path,
            run_dir=run_dir,
            attempt=attempt,
            feedback=feedback,
            judge_score_threshold=judge_score_threshold,
        )
        last_result = result

        if result["accepted"]:
            accepted_path = Path(source["chunks_path"])
            shutil.copyfile(result["candidate_chunks_path"], accepted_path)
            update_source_manifest(source_dir, "accepted", run_id, result)
            return result

        feedback = result["feedback_for_next_attempt"]

    update_source_manifest(source_dir, "failed", last_result["run_id"], last_result)
    return last_result


def run_chunk_attempt(
    source: dict,
    pages: list[dict[str, Any]],
    pages_path: Path,
    run_dir: Path,
    attempt: int,
    feedback: str,
    judge_score_threshold: int,
) -> dict:
    run_id = run_dir.name
    chunker_code = generate_chunker_script(source, pages, attempt, feedback)
    chunker_path = run_dir / "chunker.py"
    chunker_path.write_text(chunker_code, encoding="utf-8")

    raw_chunks_path = run_dir / "chunks.raw.jsonl"
    candidate_chunks_path = run_dir / "chunks.candidate.jsonl"
    validation_path = run_dir / "validation.json"
    judge_report_path = run_dir / "judge_report.json"
    feedback_path = run_dir / "feedback.txt"

    try:
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
        return build_attempt_result(
            run_id,
            accepted=False,
            candidate_chunks_path=candidate_chunks_path,
            validation=validation,
            judge_report=None,
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
        return build_attempt_result(
            run_id,
            accepted=False,
            candidate_chunks_path=candidate_chunks_path,
            validation=validation,
            judge_report=None,
            feedback_for_next_attempt=feedback_for_next_attempt,
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

    judge_report = judge_candidate_chunks(source, validation)
    write_json(judge_report_path, judge_report)

    accepted = (
        validation["passed"]
        and bool(judge_report.get("pass"))
        and int(judge_report.get("score", 0)) >= judge_score_threshold
    )
    feedback_for_next_attempt = build_feedback_for_next_attempt(validation, judge_report)
    feedback_path.write_text(feedback_for_next_attempt, encoding="utf-8")

    return build_attempt_result(
        run_id,
        accepted=accepted,
        candidate_chunks_path=candidate_chunks_path,
        validation=validation,
        judge_report=judge_report,
        feedback_for_next_attempt=feedback_for_next_attempt,
    )


def generate_chunker_script(
    source: dict,
    pages: list[dict[str, Any]],
    attempt: int,
    feedback: str,
) -> str:
    model_name = os.getenv("OPENAI_CHUNKER_MODEL", DEFAULT_CHUNKER_MODEL)
    llm = ChatOpenAI(model=model_name, temperature=0.2)
    sample_pages = compact_page_samples(pages)

    response = llm.invoke([
        (
            "system",
            "You write safe Python chunking functions for PDF text extracted page by page. "
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
                        "Prefer section headings and complete concepts as boundaries.",
                        "Target 300-900 Chinese characters per chunk when possible.",
                        "Every chunk must include the source PDF pages.",
                        "Define chunk_pages only. No file I/O. No network. No subprocess.",
                        "Allowed imports: re, math, statistics, collections, itertools, typing.",
                    ],
                    "source": {
                        "id": source["id"],
                        "display_name": source["display_name"],
                    },
                    "attempt": attempt,
                    "previous_feedback": feedback,
                    "sample_pages": sample_pages,
                },
                ensure_ascii=False,
                indent=2,
            ),
        ),
    ])

    return extract_python_code(str(response.content))


def judge_candidate_chunks(source: dict, validation: dict) -> dict:
    model_name = os.getenv("OPENAI_CHUNK_JUDGE_MODEL", DEFAULT_JUDGE_MODEL)
    llm = ChatOpenAI(model=model_name, temperature=0)
    chunks = validation.get("chunks", [])
    sample_chunks = build_chunk_samples(chunks)

    response = llm.invoke([
        (
            "system",
            "You judge chunk quality for a RAG system. Return only a JSON object.",
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
                    "sample_chunks": sample_chunks,
                    "required_json_schema": {
                        "pass": "boolean",
                        "score": "integer 0-100",
                        "problems": ["string"],
                        "feedback_for_chunker": "string",
                    },
                    "judging_rules": [
                        "Good chunks preserve exact source meaning.",
                        "Good chunks are coherent retrieval units.",
                        "Good chunks should not split one definition or explanation awkwardly.",
                        "Good chunks should not merge unrelated topics.",
                        "Reject if validation errors exist.",
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
            "pass": False,
            "score": 0,
            "problems": [f"Judge returned invalid JSON: {exc}"],
            "feedback_for_chunker": "Return valid JSON and improve chunk boundaries.",
        }

    return normalize_judge_report(report)


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

if not isinstance(chunks, list):
    raise TypeError("chunk_pages must return a list.")

with output_path.open("w", encoding="utf-8") as file:
    for chunk in chunks:
        if not isinstance(chunk, dict):
            raise TypeError("Every chunk must be a dict.")
        file.write(json.dumps(chunk, ensure_ascii=False) + "\\n")
"""


def build_attempt_result(
    run_id: str,
    accepted: bool,
    candidate_chunks_path: Path,
    validation: dict,
    judge_report: dict | None,
    feedback_for_next_attempt: str,
) -> dict:
    return {
        "run_id": run_id,
        "accepted": accepted,
        "candidate_chunks_path": str(candidate_chunks_path),
        "validation": {
            key: value for key, value in validation.items() if key != "chunks"
        },
        "judge_report": judge_report,
        "feedback_for_next_attempt": feedback_for_next_attempt,
    }


def build_feedback_for_next_attempt(
    validation: dict,
    judge_report: dict | None,
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
        judge_feedback = str(judge_report.get("feedback_for_chunker") or "")
        if problems:
            feedback_blocks.append("Judge problems:\n" + "\n".join(problems))
        if judge_feedback:
            feedback_blocks.append("Judge feedback:\n" + judge_feedback)

    if not feedback_blocks:
        return "Improve chunk coherence and preserve exact source wording."

    return "\n\n".join(feedback_blocks)


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
        "updated_at": now_iso(),
        "judge_report": result.get("judge_report") if result else None,
        "validation": result.get("validation") if result else None,
    }
    manifest_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def source_url_for_source(source: dict) -> str:
    metadata = source["metadata"]
    for key in ("viewer_url", "pdf_url", "source_url"):
        url = str(metadata.get(key) or "").strip()
        if url:
            return url

    return f"source://{source['id']}"


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
    samples = []
    selected_pages = pages[: max_pages // 2] + pages[-max_pages // 2 :]

    for page in selected_pages:
        text = str(page.get("text") or "")
        samples.append({
            "pdf_page": page.get("pdf_page"),
            "text_sample": text[:1200],
        })

    return samples


def build_chunk_samples(chunks: list[dict], max_chunks: int = 10) -> list[dict]:
    if len(chunks) <= max_chunks:
        selected = chunks
    else:
        head = chunks[: max_chunks // 2]
        tail = chunks[-max_chunks // 2 :]
        selected = head + tail

    return [
        {
            "chunk_id": chunk.get("chunk_id"),
            "pdf_pages": chunk.get("pdf_pages"),
            "chars": len(str(chunk.get("text") or "")),
            "text_sample": str(chunk.get("text") or "")[:900],
        }
        for chunk in selected
    ]


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
        raise ValueError("Judge output is not a JSON object.")

    return value


def normalize_judge_report(report: dict) -> dict:
    problems = report.get("problems") or []
    if not isinstance(problems, list):
        problems = [str(problems)]

    try:
        score = int(report.get("score", 0))
    except (TypeError, ValueError):
        score = 0

    return {
        "pass": bool(report.get("pass")),
        "score": min(max(score, 0), 100),
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
