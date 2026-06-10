from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from tcmrag.ai_chunking import (  # noqa: E402
    MIN_ACCEPTED_SEPARATION_SCORE,
    extract_pdf_pages_for_source,
    run_ai_chunking,
)
from tcmrag.source_embeddings import (  # noqa: E402
    clear_combined_vectorstore,
    combined_manifest_source_ids,
    load_combined_embedding_manifest,
    run_combined_embedding_for_sources,
    run_embedding_for_source,
)
from tcmrag.web.background_jobs import (  # noqa: E402
    discard_background_job,
    get_background_job_snapshot,
    get_background_job_snapshots,
    is_background_job_active,
    submit_background_job,
)
from tcmrag.web.chat_sessions import (  # noqa: E402
    chat_file_path,
    load_chat_sessions,
    read_chat_file,
    save_chat_session,
    session_label,
)
from tcmrag.web.citation_links import (  # noqa: E402
    CITATION_PAGE_QUERY_PARAM,
    CITATION_SOURCE_QUERY_PARAM,
    parse_positive_page,
    rewrite_markdown_citation_links,
)
from tcmrag.web.config import (  # noqa: E402
    MAX_MAX_DISTANCE,
    MIN_MAX_DISTANCE,
    clamp_max_distance,
    ensure_app_environment,
    load_app_settings,
    write_app_settings,
)
from tcmrag.web.documents import (  # noqa: E402
    chunks_window_id,
    delete_document_source,
    format_chunk_texts,
    is_uploaded_source,
    load_document_sources,
    load_source_chunks,
    local_pdf_path,
    pdf_page_count,
    pdf_window_id,
    render_pdf_page_image,
    save_uploaded_pdf,
    source_for_id,
    source_label,
)
from tcmrag.web.styles import apply_global_styles  # noqa: E402


ensure_app_environment()


st.set_page_config(
    page_title="TCM Citation RAG",
    page_icon="",
    layout="centered",
)

apply_global_styles()

app_settings = load_app_settings()

if "messages" not in st.session_state:
    st.session_state.messages = []

if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = None

if "current_chat_title" not in st.session_state:
    st.session_state.current_chat_title = "Unsaved chat"

if "max_distance" not in st.session_state:
    st.session_state.max_distance = app_settings["max_distance"]

if "app_windows" not in st.session_state:
    st.session_state.app_windows = []

if "active_top_panel" not in st.session_state:
    st.session_state.active_top_panel = "chat"

if "top_panel_selection" not in st.session_state:
    st.session_state.top_panel_selection = st.session_state.active_top_panel

if "pending_top_panel_selection" not in st.session_state:
    st.session_state.pending_top_panel_selection = None

if "active_document_window_id" not in st.session_state:
    st.session_state.active_document_window_id = "documents"

if "pending_selected_source_id" not in st.session_state:
    st.session_state.pending_selected_source_id = None

if "chunking_notice" not in st.session_state:
    st.session_state.chunking_notice = None

if "document_notice" not in st.session_state:
    st.session_state.document_notice = None

if "pdf_upload_widget_nonce" not in st.session_state:
    st.session_state.pdf_upload_widget_nonce = 0

if "background_job_ids" not in st.session_state:
    st.session_state.background_job_ids = []

def request_top_panel(panel_id: str) -> None:
    st.session_state.active_top_panel = panel_id
    st.session_state.pending_top_panel_selection = panel_id


def request_selected_source(source_id: str | None) -> None:
    st.session_state.pending_selected_source_id = source_id or ""


def normalize_selected_source_id(source_ids: list[str]) -> str | None:
    if not source_ids:
        st.session_state.pending_selected_source_id = None
        st.session_state.pop("selected_source_id", None)
        return None

    source_id_set = set(source_ids)
    pending_source_value = st.session_state.get("pending_selected_source_id")
    pending_source_id = str(pending_source_value or "")
    current_source_id = str(st.session_state.get("selected_source_id") or "")

    if pending_source_value is not None:
        selected_source_id = (
            pending_source_id
            if pending_source_id in source_id_set
            else source_ids[0]
        )
        st.session_state.pending_selected_source_id = None
        st.session_state.pop("selected_source_id", None)
        return selected_source_id

    st.session_state.pending_selected_source_id = None
    if current_source_id in source_id_set:
        return current_source_id

    selected_source_id = source_ids[0]
    st.session_state.pop("selected_source_id", None)
    return selected_source_id


def track_background_job(job_id: str) -> None:
    job_ids = list(st.session_state.background_job_ids)
    if job_id not in job_ids:
        job_ids.append(job_id)
    st.session_state.background_job_ids = job_ids


def untrack_background_job(job_id: str) -> None:
    st.session_state.background_job_ids = [
        existing_job_id
        for existing_job_id in st.session_state.background_job_ids
        if existing_job_id != job_id
    ]


def session_job_snapshots() -> list[dict[str, Any]]:
    return get_background_job_snapshots(list(st.session_state.background_job_ids))


def active_session_jobs() -> list[dict[str, Any]]:
    return [
        job
        for job in session_job_snapshots()
        if is_background_job_active(job)
    ]


def source_jobs_in_progress(source_id: str, kinds: set[str] | None = None) -> list[dict[str, Any]]:
    jobs = []
    for job in active_session_jobs():
        if kinds and str(job.get("kind") or "") not in kinds:
            continue
        metadata = job.get("metadata") or {}
        if str(metadata.get("source_id") or "") == source_id:
            jobs.append(job)
    return jobs


def source_job_in_progress(source_id: str, kinds: set[str] | None = None) -> bool:
    return bool(source_jobs_in_progress(source_id, kinds))


def any_document_job_in_progress() -> bool:
    document_kinds = {
        "document_processing",
        "pdf_extraction",
        "chunk_generation",
        "source_embedding",
        "combined_embedding",
        "delete_vectorstore_sync",
    }
    return any(str(job.get("kind") or "") in document_kinds for job in active_session_jobs())


def chat_job_in_progress() -> bool:
    return any(str(job.get("kind") or "") == "chat_answer" for job in active_session_jobs())


def combined_embedding_job_in_progress() -> bool:
    return any(
        str(job.get("kind") or "") in {"combined_embedding", "document_processing"}
        for job in active_session_jobs()
    )


def clamp_job_progress(value: Any) -> float:
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return 0.0


def job_error_message(job: dict[str, Any]) -> str:
    exception_type = str(job.get("exception_type") or "").strip()
    error = str(job.get("error") or "").strip()
    if exception_type and error:
        return f"{exception_type}: {error}"
    return error or "Unknown job failure."


def replace_pending_chat_message(job_id: str, message: dict[str, Any]) -> None:
    for index, existing in enumerate(st.session_state.messages):
        if str(existing.get("pending_job_id") or "") == job_id:
            st.session_state.messages[index] = message
            return

    st.session_state.messages.append(message)


def submit_pdf_extraction_job(source: dict) -> str:
    def worker(source_record: dict, progress_callback=None):
        if progress_callback is not None:
            progress_callback({
                "progress": 0.1,
                "message": "Extracting text from PDF.",
            })
        return extract_pdf_pages_for_source(source_record)

    return submit_background_job(
        kind="pdf_extraction",
        label=f"Extracting PDF for {source['display_name']}",
        target=worker,
        args=(source,),
        metadata={"source_id": source["id"]},
        progress_kwarg="progress_callback",
    )


def submit_chunk_generation_job(source: dict) -> str:
    return submit_background_job(
        kind="chunk_generation",
        label=f"Generating chunks for {source['display_name']}",
        target=run_ai_chunking,
        args=(source,),
        metadata={"source_id": source["id"]},
        progress_kwarg="progress_callback",
    )


def submit_source_embedding_job(source: dict) -> str:
    def worker(source_record: dict, progress_callback=None):
        if progress_callback is not None:
            progress_callback({
                "progress": 0.1,
                "message": "Embedding chunks and evaluating retrieval distances.",
            })
        return run_embedding_for_source(source_record)

    return submit_background_job(
        kind="source_embedding",
        label=f"Embedding chunks for {source['display_name']}",
        target=worker,
        args=(source,),
        metadata={"source_id": source["id"]},
        progress_kwarg="progress_callback",
    )


def submit_combined_embedding_job(sources: list[dict], notice_source_id: str) -> str:
    def worker(source_records: list[dict], progress_callback=None):
        if progress_callback is not None:
            progress_callback({
                "progress": 0.1,
                "message": "Building combined vectorstore.",
            })
        return run_combined_embedding_for_sources(source_records)

    return submit_background_job(
        kind="combined_embedding",
        label="Building combined vectorstore",
        target=worker,
        args=(sources,),
        metadata={"notice_source_id": notice_source_id},
        progress_kwarg="progress_callback",
    )


def submit_document_processing_job(source: dict) -> str:
    def report_pipeline_progress(
        progress_callback,
        progress: float,
        message: str,
        **event_fields,
    ) -> None:
        if progress_callback is None:
            return

        progress_callback({
            "progress": progress,
            "message": message,
            **event_fields,
        })

    def reload_source(source_id: str) -> dict:
        source_record = source_for_id(source_id)
        if source_record is None:
            raise FileNotFoundError(f"Document source not found: {source_id}")
        return source_record

    def worker(source_record: dict, progress_callback=None):
        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY is required to process documents.")

        source_id = source_record["id"]
        report_pipeline_progress(
            progress_callback,
            0.03,
            "Step 1/4: extracting PDF text.",
        )
        extraction = extract_pdf_pages_for_source(source_record)
        if extraction.get("status") != "extracted":
            raise RuntimeError(extraction.get("error") or "PDF extraction failed.")

        report_pipeline_progress(
            progress_callback,
            0.14,
            (
                "Step 1/4 complete: extracted "
                f"{extraction.get('non_empty_page_count', 'unknown')} text pages."
            ),
        )

        chunk_progress_start = 0.16
        chunk_progress_span = 0.54

        def report_chunking_progress(event: dict[str, Any]) -> None:
            chunk_progress = clamp_job_progress(event.get("progress", 0.0))
            report_pipeline_progress(
                progress_callback,
                chunk_progress_start + (chunk_progress * chunk_progress_span),
                f"Step 2/4: {event.get('message') or 'generating chunks.'}",
                feedback=event.get("feedback", ""),
                feedback_title=event.get("feedback_title", ""),
                attempt=event.get("attempt"),
                max_attempts=event.get("max_attempts"),
                stage=event.get("stage"),
                run_id=event.get("run_id"),
            )

        chunking = run_ai_chunking(
            reload_source(source_id),
            progress_callback=report_chunking_progress,
        )
        if not chunking.get("accepted"):
            raise RuntimeError("Chunk generation did not produce accepted chunks.")

        report_pipeline_progress(
            progress_callback,
            0.72,
            f"Step 2/4 complete: accepted chunks from {chunking.get('run_id', 'unknown')}.",
        )

        report_pipeline_progress(
            progress_callback,
            0.76,
            "Step 3/4: embedding document chunks.",
        )
        embedding = run_embedding_for_source(reload_source(source_id))
        report_pipeline_progress(
            progress_callback,
            0.86,
            (
                "Step 3/4 complete: embedded "
                f"{embedding.get('chunk_count', 'unknown')} chunks."
            ),
        )

        report_pipeline_progress(
            progress_callback,
            0.90,
            "Step 4/4: rebuilding combined vectorstore.",
        )
        combined_embedding = run_combined_embedding_for_sources(load_document_sources())
        report_pipeline_progress(
            progress_callback,
            0.98,
            (
                "Step 4/4 complete: combined "
                f"{combined_embedding.get('source_count', 'unknown')} sources."
            ),
        )

        return {
            "status": "processed",
            "source_id": source_id,
            "extraction": extraction,
            "chunking": chunking,
            "embedding": embedding,
            "combined_embedding": combined_embedding,
        }

    return submit_background_job(
        kind="document_processing",
        label=f"Processing {source['display_name']}",
        target=worker,
        args=(source,),
        metadata={"source_id": source["id"]},
        progress_kwarg="progress_callback",
    )


def submit_delete_vectorstore_sync_job(deleted_source: dict) -> str:
    def worker(source_record: dict, progress_callback=None):
        if progress_callback is not None:
            progress_callback({
                "progress": 0.1,
                "message": "Updating combined vectorstore after deletion.",
            })
        return sync_combined_vectorstore_after_document_delete(source_record)

    return submit_background_job(
        kind="delete_vectorstore_sync",
        label="Updating combined vectorstore after deletion",
        target=worker,
        args=(deleted_source,),
        progress_kwarg="progress_callback",
    )


def apply_completed_chat_job(job: dict[str, Any]) -> None:
    if str(job.get("status") or "") == "completed":
        result = job.get("result") or {}
        assistant_message = {
            "role": "assistant",
            "content": result.get("answer", ""),
            "sources": result.get("sources", []),
            "scores": result.get("scores", []),
            "search_question": result.get("search_question"),
            "max_distance": result.get("max_distance", clamp_max_distance(st.session_state.max_distance)),
            "vectorstore_path": result.get("vectorstore_path"),
        }
    else:
        error_text = job_error_message(job)
        assistant_message = {
            "role": "assistant",
            "content": "The RAG pipeline failed to run.",
            "job_error": error_text,
        }

    replace_pending_chat_message(str(job["id"]), assistant_message)
    save_current_chat()


def apply_completed_pdf_extraction_job(job: dict[str, Any]) -> None:
    source_id = str((job.get("metadata") or {}).get("source_id") or "")
    if str(job.get("status") or "") == "completed":
        result = job.get("result") or {}
        if result.get("status") == "extracted":
            st.session_state.chunking_notice = {
                "source_id": source_id,
                "kind": "success",
                "message": (
                    "PDF text extracted: "
                    f"`{result['non_empty_page_count']}` text pages out of "
                    f"`{result['page_count']}`."
                ),
            }
        else:
            st.session_state.chunking_notice = {
                "source_id": source_id,
                "kind": "error",
                "message": result.get("error") or "PDF extraction failed.",
            }
        return

    st.session_state.chunking_notice = {
        "source_id": source_id,
        "kind": "error",
        "message": f"PDF extraction failed: {job_error_message(job)}",
    }


def apply_completed_chunk_generation_job(job: dict[str, Any]) -> None:
    source_id = str((job.get("metadata") or {}).get("source_id") or "")
    if str(job.get("status") or "") != "completed":
        st.session_state.chunking_notice = {
            "source_id": source_id,
            "kind": "error",
            "message": f"Chunking failed: {job_error_message(job)}",
        }
        return

    result = job.get("result") or {}
    if result.get("accepted"):
        accepted_reason = str(result.get("accepted_reason") or "").strip()
        if accepted_reason == "separation_score_threshold":
            separation = (result.get("retrieval_evaluation") or {}).get("separation_score")
            message = (
                f"Chunks accepted from `{result['run_id']}` because retrieval "
                f"separation `{format_distance(separation)}` exceeded "
                f"`{MIN_ACCEPTED_SEPARATION_SCORE:.1f}`."
            )
        elif accepted_reason == "highest_separation_score_fallback":
            separation = (result.get("retrieval_evaluation") or {}).get("separation_score")
            message = (
                f"No run exceeded `{MIN_ACCEPTED_SEPARATION_SCORE:.1f}`. "
                f"Accepted `{result['run_id']}` with the highest retrieval "
                f"separation `{format_distance(separation)}`."
            )
        elif result.get("forced_acceptance"):
            message = (
                f"Chunks accepted from `{result['run_id']}` "
                f"on attempt `{result.get('attempt', 'unknown')}` / "
                f"`{result.get('max_attempts', 'unknown')}` "
                "because the maximum number of attempts was reached."
            )
        else:
            message = (
                f"Chunks accepted from `{result['run_id']}` "
                f"on attempt `{result.get('attempt', 'unknown')}` / "
                f"`{result.get('max_attempts', 'unknown')}`."
            )
        st.session_state.chunking_notice = {
            "source_id": source_id,
            "kind": "success",
            "message": message,
        }
        return

    st.session_state.chunking_notice = {
        "source_id": source_id,
        "kind": "error",
        "message": (
            "Chunking did not produce a valid retrieval separation run. "
            f"Latest run: `{result.get('run_id', 'unknown')}` "
            f"attempt `{result.get('attempt', 'unknown')}` / "
            f"`{result.get('max_attempts', 'unknown')}`."
        ),
    }


def apply_completed_source_embedding_job(job: dict[str, Any]) -> None:
    source_id = str((job.get("metadata") or {}).get("source_id") or "")
    try:
        from tcmrag.rag import clear_rag_cache

        clear_rag_cache()
    except Exception:
        pass

    if str(job.get("status") or "") != "completed":
        st.session_state.chunking_notice = {
            "source_id": source_id,
            "kind": "error",
            "message": f"Embedding failed: {job_error_message(job)}",
        }
        return

    result = job.get("result") or {}
    evaluation = result.get("evaluation") or {}
    st.session_state.chunking_notice = {
        "source_id": source_id,
        "kind": "success",
        "message": (
            f"Embedded `{result.get('chunk_count', 'unknown')}` chunks. "
            f"Avg top-k good distance: "
            f"`{format_distance(evaluation.get('good_avg_top_k_distance'))}`; "
            f"bad distance: "
            f"`{format_distance(evaluation.get('bad_avg_top_k_distance'))}`."
        ),
    }


def apply_completed_combined_embedding_job(job: dict[str, Any]) -> None:
    notice_source_id = str((job.get("metadata") or {}).get("notice_source_id") or "")
    try:
        from tcmrag.rag import clear_rag_cache

        clear_rag_cache()
    except Exception:
        pass

    if str(job.get("status") or "") != "completed":
        st.session_state.chunking_notice = {
            "source_id": notice_source_id,
            "kind": "error",
            "message": f"Combined embedding failed: {job_error_message(job)}",
        }
        return

    result = job.get("result") or {}
    evaluation = result.get("evaluation") or {}
    st.session_state.chunking_notice = {
        "source_id": notice_source_id,
        "kind": "success",
        "message": (
            f"Built combined vectorstore from `{result.get('source_count', 'unknown')}` sources "
            f"and `{result.get('chunk_count', 'unknown')}` chunks. "
            f"Good avg: `{format_distance(evaluation.get('good_avg_top_k_distance'))}`; "
            f"bad avg: `{format_distance(evaluation.get('bad_avg_top_k_distance'))}`."
        ),
    }


def apply_completed_document_processing_job(job: dict[str, Any]) -> None:
    source_id = str((job.get("metadata") or {}).get("source_id") or "")
    try:
        from tcmrag.rag import clear_rag_cache

        clear_rag_cache()
    except Exception:
        pass

    if str(job.get("status") or "") != "completed":
        st.session_state.chunking_notice = {
            "source_id": source_id,
            "kind": "error",
            "message": f"Document processing failed: {job_error_message(job)}",
        }
        return

    result = job.get("result") or {}
    extraction = result.get("extraction") or {}
    chunking = result.get("chunking") or {}
    embedding = result.get("embedding") or {}
    combined_embedding = result.get("combined_embedding") or {}
    chunker_run = str(chunking.get("run_id") or "unknown")
    separation = (chunking.get("retrieval_evaluation") or {}).get("separation_score")

    st.session_state.chunking_notice = {
        "source_id": source_id,
        "kind": "success",
        "message": (
            "Document processed: "
            f"extracted `{extraction.get('non_empty_page_count', 'unknown')}` text pages, "
            f"accepted chunker run `{chunker_run}` "
            f"with retrieval gap `{format_distance(separation)}`, "
            f"embedded `{embedding.get('chunk_count', 'unknown')}` chunks, "
            f"and rebuilt the combined vectorstore from "
            f"`{combined_embedding.get('source_count', 'unknown')}` sources."
        ),
    }


def apply_completed_delete_vectorstore_sync_job(job: dict[str, Any]) -> None:
    if str(job.get("status") or "") != "completed":
        st.session_state.document_notice = {
            "kind": "error",
            "message": (
                "The document was deleted, but updating the combined vectorstore failed. "
                "Please rebuild the combined vectorstore manually."
            ),
        }
        return

    result = job.get("result")
    if result == "rebuilt":
        message = "Uploaded document deleted. Combined vectorstore rebuilt."
    elif result == "cleared":
        message = "Uploaded document deleted. Combined vectorstore cleared."
    elif result == "cleared_no_key":
        message = (
            "Uploaded document deleted. Combined vectorstore was cleared because "
            "rebuilding it requires OPENAI_API_KEY."
        )
    else:
        message = "Uploaded document deleted."

    st.session_state.document_notice = {
        "kind": "success",
        "message": message,
    }


def apply_completed_background_job(job: dict[str, Any]) -> None:
    kind = str(job.get("kind") or "")
    if kind == "chat_answer":
        apply_completed_chat_job(job)
        return
    if kind == "pdf_extraction":
        apply_completed_pdf_extraction_job(job)
        return
    if kind == "chunk_generation":
        apply_completed_chunk_generation_job(job)
        return
    if kind == "source_embedding":
        apply_completed_source_embedding_job(job)
        return
    if kind == "combined_embedding":
        apply_completed_combined_embedding_job(job)
        return
    if kind == "document_processing":
        apply_completed_document_processing_job(job)
        return
    if kind == "delete_vectorstore_sync":
        apply_completed_delete_vectorstore_sync_job(job)


def sync_background_jobs(trigger_rerun_on_change: bool = False) -> bool:
    changed = False
    for job_id in list(st.session_state.background_job_ids):
        job = get_background_job_snapshot(job_id)
        if job is None:
            untrack_background_job(job_id)
            changed = True
            continue

        if is_background_job_active(job):
            continue

        apply_completed_background_job(job)
        discard_background_job(job_id)
        untrack_background_job(job_id)
        changed = True

    if changed and trigger_rerun_on_change:
        st.rerun()

    return changed


def query_param_text(name: str) -> str:
    value = st.query_params.get(name, "")
    if isinstance(value, list):
        value = value[-1] if value else ""
    return str(value or "")


def renderable_markdown(markdown_text: str) -> str:
    return rewrite_markdown_citation_links(markdown_text, load_document_sources())


def render_document_notice() -> None:
    notice = st.session_state.get("document_notice")
    if not isinstance(notice, dict):
        return

    message = str(notice.get("message") or "").strip()
    if not message:
        st.session_state.document_notice = None
        return

    if notice.get("kind") == "error":
        st.error(message)
    else:
        st.success(message)

    st.session_state.document_notice = None


def render_assistant_details(message: dict) -> None:
    job_error = str(message.get("job_error") or "").strip()
    sources = message.get("sources")

    if job_error:
        with st.expander("Job error"):
            st.code(job_error, language="text")

    if sources:
        with st.expander("Sources"):
            for index, source in enumerate(sources, start=1):
                citation = source.get("citation_markdown", "No citation")
                page = source.get("pdf_page", "unknown")

                st.markdown(f"**Source {index} - page {page}**")
                st.markdown(renderable_markdown(citation))
                st.json(source)


def render_chat_message(message: dict) -> None:
    pending_job_id = str(message.get("pending_job_id") or "").strip()
    if pending_job_id:
        st.markdown(message["content"])
        job = get_background_job_snapshot(pending_job_id)
        if job is not None:
            st.progress(
                clamp_job_progress(job.get("progress", 0.0)),
                text=str(job.get("message") or "Answer in progress."),
            )
        return

    st.markdown(renderable_markdown(message["content"]))

    if message["role"] == "assistant":
        render_assistant_details(message)


def render_streamed_markdown(chunks) -> str:
    placeholder = st.empty()
    collected_chunks = []

    for chunk in chunks:
        text = str(chunk or "")
        if not text:
            continue

        collected_chunks.append(text)
        placeholder.markdown(renderable_markdown("".join(collected_chunks)) + "▌")

    answer = "".join(collected_chunks)
    placeholder.markdown(renderable_markdown(answer))
    return answer


def assistant_message_from_rag_result(result: dict) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": result.get("answer", ""),
        "sources": result.get("sources", []),
        "scores": result.get("scores", []),
        "search_question": result.get("search_question"),
        "max_distance": result.get("max_distance", clamp_max_distance(st.session_state.max_distance)),
        "vectorstore_path": result.get("vectorstore_path"),
    }


def save_app_settings() -> None:
    st.session_state.max_distance = clamp_max_distance(st.session_state.max_distance)
    write_app_settings(st.session_state.max_distance)


def current_vectorstore_label() -> str:
    try:
        from tcmrag.rag import active_vectorstore_label

        return active_vectorstore_label()
    except Exception:
        return "No vectorstore available."


def rag_vectorstore_available() -> bool:
    try:
        from tcmrag.rag import vectorstore_available

        return vectorstore_available()
    except Exception:
        return False


def open_chunks_window(source: dict) -> None:
    window_id = chunks_window_id(source["id"])
    windows = list(st.session_state.app_windows)

    if not any(window.get("id") == window_id for window in windows):
        windows.append({
            "id": window_id,
            "title": f"{source['display_name']} chunks",
            "type": "chunks",
            "source_id": source["id"],
        })

    st.session_state.app_windows = windows
    request_selected_source(source["id"])
    request_top_panel("documents")
    st.session_state.active_document_window_id = window_id


def open_pdf_window(source: dict) -> None:
    window_id = pdf_window_id(source["id"])
    windows = list(st.session_state.app_windows)

    if not any(window.get("id") == window_id for window in windows):
        windows.append({
            "id": window_id,
            "title": f"{source['display_name']} PDF",
            "type": "pdf",
            "source_id": source["id"],
        })

    st.session_state.app_windows = windows
    request_selected_source(source["id"])
    request_top_panel("documents")
    st.session_state.active_document_window_id = window_id


def handle_citation_navigation() -> None:
    source_id = query_param_text(CITATION_SOURCE_QUERY_PARAM).strip()
    page = parse_positive_page(query_param_text(CITATION_PAGE_QUERY_PARAM))

    if not source_id or page is None:
        return

    source = source_for_id(source_id)
    st.query_params.clear()

    if source is None:
        st.rerun()

    request_selected_source(source_id)
    open_pdf_window(source)
    st.session_state[f"pdf_page_{source_id}"] = page
    st.session_state.active_document_window_id = pdf_window_id(source_id)
    st.rerun()


def close_window(window_id: str) -> None:
    st.session_state.app_windows = [
        window for window in st.session_state.app_windows if window.get("id") != window_id
    ]

    if st.session_state.active_document_window_id == window_id:
        st.session_state.active_document_window_id = next_available_document_window_id()


def close_source_windows(source_id: str) -> None:
    closed_window_ids = {
        window.get("id")
        for window in st.session_state.app_windows
        if window.get("source_id") == source_id
    }
    st.session_state.app_windows = [
        window
        for window in st.session_state.app_windows
        if window.get("source_id") != source_id
    ]

    if st.session_state.active_document_window_id in closed_window_ids:
        st.session_state.active_document_window_id = next_available_document_window_id()


def next_available_document_window_id() -> str:
    windows = list(st.session_state.app_windows)
    if windows:
        return str(windows[0].get("id") or "documents")
    return "documents"


def active_source_id_from_windows(windows: list[dict]) -> str | None:
    active_window_id = st.session_state.active_document_window_id

    for window in windows:
        if window.get("id") != active_window_id:
            continue

        source_id = str(window.get("source_id") or "").strip()
        if source_id:
            return source_id

    return None


def sync_document_window_state() -> None:
    valid_source_ids = {
        source["id"]
        for source in load_document_sources()
    }
    windows = list(st.session_state.app_windows)
    filtered_windows = [
        window
        for window in windows
        if not window.get("source_id") or window.get("source_id") in valid_source_ids
    ]

    if len(filtered_windows) != len(windows):
        st.session_state.app_windows = filtered_windows

    valid_window_ids = {"documents"} | {
        str(window.get("id") or "")
        for window in filtered_windows
    }
    if st.session_state.active_document_window_id not in valid_window_ids:
        st.session_state.active_document_window_id = next_available_document_window_id()

    active_source_id = active_source_id_from_windows(filtered_windows)
    if active_source_id and active_source_id in valid_source_ids:
        request_selected_source(active_source_id)


def render_pdf_upload() -> None:
    widget_key = f"pdf_upload_input_{st.session_state.pdf_upload_widget_nonce}"
    st.file_uploader(
        "Upload PDF",
        type=["pdf"],
        accept_multiple_files=False,
        key=widget_key,
        on_change=handle_pdf_upload_selection,
        args=(widget_key,),
        help="Select a PDF and it will be saved immediately.",
    )


def handle_pdf_upload_selection(widget_key: str) -> None:
    uploaded_pdf = st.session_state.get(widget_key)
    if uploaded_pdf is None:
        return

    try:
        metadata = save_uploaded_pdf(uploaded_pdf)
    except Exception as exc:
        st.session_state.document_notice = {
            "kind": "error",
            "message": f"Could not save the uploaded PDF: {exc}",
        }
        st.session_state.pdf_upload_widget_nonce += 1
        return

    request_selected_source(metadata["id"])
    request_top_panel("documents")
    st.session_state.active_document_window_id = "documents"
    st.session_state.document_notice = {
        "kind": "success",
        "message": "PDF saved. Chunking has not been run yet.",
    }
    st.session_state.pdf_upload_widget_nonce += 1


def sync_combined_vectorstore_after_document_delete(deleted_source: dict) -> str | None:
    if deleted_source["id"] not in combined_manifest_source_ids():
        return None

    remaining_sources = load_document_sources()

    try:
        from tcmrag.rag import clear_rag_cache
    except Exception:
        clear_rag_cache = None

    if not remaining_sources or not os.getenv("OPENAI_API_KEY"):
        clear_combined_vectorstore()
        if clear_rag_cache is not None:
            clear_rag_cache()

        if not remaining_sources:
            return "cleared"

        return "cleared_no_key"

    try:
        run_combined_embedding_for_sources(remaining_sources)
    except ValueError:
        clear_combined_vectorstore()
        if clear_rag_cache is not None:
            clear_rag_cache()
        return "cleared"

    if clear_rag_cache is not None:
        clear_rag_cache()

    return "rebuilt"


def render_delete_document_control(source: dict) -> None:
    if not is_uploaded_source(source):
        return

    with st.expander("Delete uploaded document"):
        st.warning("This removes the uploaded PDF folder from docs/sources.")
        confirm_key = f"confirm_delete_source_{source['id']}"
        confirmed = st.checkbox(
            f"Delete {source['display_name']}",
            key=confirm_key,
        )

        if st.button(
            "Delete uploaded document",
            disabled=not confirmed or source_job_in_progress(source["id"]) or combined_embedding_job_in_progress(),
            use_container_width=True,
        ):
            try:
                delete_document_source(source)
            except Exception as exc:
                st.error("Could not delete this uploaded document.")
                st.exception(exc)
                return

            combined_sync_job_id = None
            if source["id"] in combined_manifest_source_ids():
                combined_sync_job_id = submit_delete_vectorstore_sync_job(source)
                track_background_job(combined_sync_job_id)

            close_source_windows(source["id"])
            remaining_sources = load_document_sources()
            remaining_source_ids = [item["id"] for item in remaining_sources]
            request_selected_source(remaining_source_ids[0] if remaining_source_ids else None)
            request_top_panel("documents")
            st.session_state.pop(f"pdf_page_{source['id']}", None)
            st.session_state.pop(confirm_key, None)

            if combined_sync_job_id is not None:
                st.session_state.document_notice = {
                    "kind": "success",
                    "message": "Uploaded document deleted. Combined vectorstore update started in the background.",
                }
            else:
                st.session_state.document_notice = {
                    "kind": "success",
                    "message": "Uploaded document deleted.",
                }

            st.rerun()


def render_chunking_notice(source: dict) -> None:
    notice = st.session_state.get("chunking_notice")
    if not notice or notice.get("source_id") != source["id"]:
        return

    if notice.get("kind") == "success":
        st.success(notice["message"])
    else:
        st.error(notice["message"])

    st.session_state.chunking_notice = None


def truncate_chunking_feedback(text: str, limit: int = 3000) -> str:
    content = str(text or "").strip()
    if len(content) <= limit:
        return content
    return content[: limit - 17].rstrip() + "\n\n[feedback truncated]"


@st.fragment(run_every="2s")
def render_active_jobs_panel() -> None:
    sync_background_jobs(trigger_rerun_on_change=True)
    jobs = active_session_jobs()
    if not jobs:
        return

    st.subheader("Active jobs")
    for job in jobs:
        label = str(job.get("label") or "Background job")
        message = str(job.get("message") or label)
        st.caption(label)
        st.progress(clamp_job_progress(job.get("progress", 0.0)), text=message)
        run_id = str((job.get("metadata") or {}).get("run_id") or "").strip()
        if run_id:
            st.caption(f"Chunker run: `{run_id}`")

        feedback = truncate_chunking_feedback(str(job.get("feedback") or ""))
        if feedback:
            feedback_title = str(job.get("feedback_title") or "Latest feedback")
            with st.expander(feedback_title):
                st.code(feedback, language="text")


def render_chunking_status(source: dict) -> None:
    chunking = source["metadata"].get("chunking")
    if not isinstance(chunking, dict):
        return

    status = str(chunking.get("status") or "unknown")
    latest_run_id = str(chunking.get("latest_run_id") or "unknown")
    st.caption(f"Chunking status: `{status}` from `{latest_run_id}`")

    attempt_label = format_chunking_attempt_label(chunking)
    if attempt_label:
        st.caption(f"Chunk generation attempt: {attempt_label}")

    if chunking.get("forced_acceptance"):
        st.caption("Accepted after reaching the maximum number of attempts.")

    accepted_reason = str(chunking.get("accepted_reason") or "").strip()
    if accepted_reason == "separation_score_threshold":
        st.caption(
            "Accepted because retrieval separation exceeded "
            f"`{MIN_ACCEPTED_SEPARATION_SCORE:.1f}`."
        )
    elif accepted_reason == "highest_separation_score_fallback":
        st.caption(
            "Accepted as the highest-separation run after all attempts stayed "
            f"below `{MIN_ACCEPTED_SEPARATION_SCORE:.1f}`."
        )

    judge_report = chunking.get("judge_report")
    if isinstance(judge_report, dict):
        reasoning_summary = str(judge_report.get("reasoning_summary") or "").strip()
        feedback = str(judge_report.get("feedback_for_chunker") or "").strip()
        if reasoning_summary or feedback:
            with st.expander("Chunker feedback"):
                if reasoning_summary:
                    st.write(reasoning_summary)
                if feedback:
                    st.write(feedback)

    retrieval_evaluation = chunking.get("retrieval_evaluation")
    if isinstance(retrieval_evaluation, dict):
        top_k = retrieval_evaluation.get("top_k", 5)
        good_avg = retrieval_evaluation.get("good_avg_top_k_distance")
        bad_avg = retrieval_evaluation.get("bad_avg_top_k_distance")
        separation = retrieval_evaluation.get("separation_score")
        st.caption(
            f"Run retrieval gap top k=`{top_k}`: "
            f"good `{format_distance(good_avg)}`, "
            f"bad `{format_distance(bad_avg)}`, "
            f"gap `{format_distance(separation)}`."
        )

    validation = chunking.get("validation")
    if isinstance(validation, dict):
        deterministic_warnings = []
        for validation_key in ("errors", "warnings"):
            values = validation.get(validation_key)
            if isinstance(values, list):
                deterministic_warnings.extend(
                    str(value).strip()
                    for value in values
                    if str(value).strip()
                )
        if deterministic_warnings:
            st.warning(
                "Deterministic validation warning: "
                f"{deterministic_warnings[0]}"
            )


def render_embedding_status(source: dict) -> None:
    embedding = source["metadata"].get("embedding")
    if not isinstance(embedding, dict):
        return

    status = str(embedding.get("status") or "unknown")
    model = str(embedding.get("model") or "unknown")
    vectorstore_path = str(embedding.get("vectorstore_path") or "unknown")
    chunk_count = embedding.get("chunk_count", "unknown")
    st.caption(
        f"Embedding status: `{status}` using `{model}` "
        f"for `{chunk_count}` chunks."
    )
    st.caption(f"Vectorstore: `{vectorstore_path}`")

    evaluation = embedding.get("evaluation")
    if isinstance(evaluation, dict):
        top_k = evaluation.get("top_k", 5)
        good_avg = evaluation.get("good_avg_top_k_distance")
        bad_avg = evaluation.get("bad_avg_top_k_distance")
        st.caption(
            f"Avg distance top k=`{top_k}`: "
            f"good `{format_distance(good_avg)}`, "
            f"bad `{format_distance(bad_avg)}`."
        )


def render_combined_embedding_status() -> None:
    manifest = load_combined_embedding_manifest()
    if not manifest:
        return

    status = str(manifest.get("status") or "unknown")
    model = str(manifest.get("model") or "unknown")
    source_count = manifest.get("source_count", "unknown")
    chunk_count = manifest.get("chunk_count", "unknown")
    vectorstore_path = str(manifest.get("vectorstore_path") or "unknown")
    st.caption(
        f"Combined vectorstore: `{status}` using `{model}` "
        f"from `{source_count}` sources and `{chunk_count}` chunks."
    )
    st.caption(f"Combined path: `{vectorstore_path}`")

    combined_names = combined_source_names(manifest)
    if combined_names:
        st.caption(f"Included documents: {combined_names}")

    evaluation = manifest.get("evaluation")
    if isinstance(evaluation, dict):
        top_k = evaluation.get("top_k", 5)
        good_avg = evaluation.get("good_avg_top_k_distance")
        bad_avg = evaluation.get("bad_avg_top_k_distance")
        st.caption(
            f"Combined avg distance top k=`{top_k}`: "
            f"good `{format_distance(good_avg)}`, "
            f"bad `{format_distance(bad_avg)}`."
        )


def combined_source_names(manifest: dict | None) -> str:
    if not isinstance(manifest, dict):
        return ""

    sources = manifest.get("sources")
    if not isinstance(sources, list):
        return ""

    names = []
    for source in sources:
        if not isinstance(source, dict):
            continue

        name = str(source.get("display_name") or source.get("id") or "").strip()
        if name:
            names.append(name)

    return ", ".join(names)


def format_distance(value) -> str:
    try:
        return f"{float(value):.6f}"
    except (TypeError, ValueError):
        return "unknown"


def format_chunking_attempt_label(chunking: dict) -> str:
    attempt = chunking.get("attempt")
    max_attempts = chunking.get("max_attempts")

    if attempt is None:
        run_id = str(chunking.get("latest_run_id") or "")
        match = re.search(r"_(\d+)_[0-9a-f]{8}$", run_id)
        if match:
            attempt = match.group(1)

    if attempt in (None, 0, "0"):
        return ""

    if max_attempts in (None, 0, "0"):
        return f"`{attempt}`"

    return f"`{attempt}` / `{max_attempts}`"


def extracted_pages_ready(source: dict) -> bool:
    extraction = source["metadata"].get("pdf_extraction")
    if not isinstance(extraction, dict):
        return False

    pages_filename = str(extraction.get("pages_path") or "pages.json")
    pages_path = Path(source["source_dir"]) / pages_filename
    return extraction.get("status") == "extracted" and pages_path.exists()


def render_pdf_extraction_status(source: dict) -> None:
    extraction = source["metadata"].get("pdf_extraction")
    if not isinstance(extraction, dict):
        return

    status = str(extraction.get("status") or "unknown")
    page_count = extraction.get("page_count", "unknown")
    non_empty_page_count = extraction.get("non_empty_page_count", "unknown")
    st.caption(
        "PDF extraction: "
        f"`{status}` with `{non_empty_page_count}` text pages out of `{page_count}`."
    )

    error = str(extraction.get("error") or "").strip()
    if status == "failed" and error:
        st.warning(error)


def render_combined_embedding_control(sources: list[dict], notice_source_id: str) -> None:
    manifest = load_combined_embedding_manifest()
    label = "Rebuild combined vectorstore" if manifest else "Build combined vectorstore"
    has_chunks = any(Path(source["chunks_path"]).exists() for source in sources)
    combined_job_active = any_document_job_in_progress()

    if st.button(
        label,
        disabled=not has_chunks or combined_job_active,
        help="Build one FAISS vectorstore from all sources that have chunks.",
        use_container_width=True,
    ):
        if not os.getenv("OPENAI_API_KEY"):
            st.session_state.chunking_notice = {
                "source_id": notice_source_id,
                "kind": "error",
                "message": "OPENAI_API_KEY is required to build the combined vectorstore.",
            }
            st.rerun()

        job_id = submit_combined_embedding_job(sources, notice_source_id)
        track_background_job(job_id)
        st.session_state.chunking_notice = {
            "source_id": notice_source_id,
            "kind": "success",
            "message": "Combined vectorstore build started in the background.",
        }
        st.rerun()


def render_document_processing_control(source: dict, pdf_path: Path | None) -> None:
    if not is_uploaded_source(source):
        return

    has_outputs = (
        extracted_pages_ready(source)
        or Path(source["chunks_path"]).exists()
        or isinstance(source["metadata"].get("embedding"), dict)
        or source["id"] in combined_manifest_source_ids()
    )
    label = "Reprocess document" if has_outputs else "Process document"
    processing_in_progress = any_document_job_in_progress()

    if st.button(
        label,
        disabled=pdf_path is None or processing_in_progress,
        help=(
            "Extract PDF text, generate chunks, embed this document, "
            "then rebuild the combined vectorstore."
        ),
        use_container_width=True,
    ):
        if pdf_path is None:
            st.session_state.chunking_notice = {
                "source_id": source["id"],
                "kind": "error",
                "message": "No PDF file found for this document.",
            }
            st.rerun()

        if not os.getenv("OPENAI_API_KEY"):
            st.session_state.chunking_notice = {
                "source_id": source["id"],
                "kind": "error",
                "message": (
                    "OPENAI_API_KEY is required to extract, chunk, embed, "
                    "and rebuild the combined vectorstore."
                ),
            }
            st.rerun()

        job_id = submit_document_processing_job(source)
        track_background_job(job_id)
        st.session_state.chunking_notice = {
            "source_id": source["id"],
            "kind": "success",
            "message": "Document processing started in the background.",
        }
        st.rerun()


def render_document_window() -> None:
    st.title("Documents")
    render_document_notice()
    sources = load_document_sources()

    if not sources:
        st.info("No documents found.")
        render_pdf_upload()
        return

    source_by_id = {source["id"]: source for source in sources}
    source_ids = list(source_by_id)
    current_source_id = normalize_selected_source_id(source_ids)
    selected_index = source_ids.index(current_source_id)

    selected_source_id = st.selectbox(
        "Documents",
        source_ids,
        index=selected_index,
        format_func=lambda source_id: source_label(source_by_id[source_id]),
        key="selected_source_id",
    )
    source = source_by_id[selected_source_id]
    chunks = load_source_chunks(source["chunks_path"])
    pdf_path = local_pdf_path(source)

    st.write(f"Document: `{source_label(source)}`")
    render_chunking_notice(source)
    render_pdf_extraction_status(source)
    render_chunking_status(source)
    render_embedding_status(source)

    st.caption(f"Chunks: `{len(chunks)}`")

    if st.button("Open PDF window", disabled=pdf_path is None, use_container_width=True):
        open_pdf_window(source)
        st.rerun()

    if st.button(
        "Open chunk texts window",
        disabled=not chunks,
        use_container_width=True,
    ):
        open_chunks_window(source)
        st.rerun()

    if not chunks:
        st.info("No chunks found for this document.")

    if is_uploaded_source(source):
        render_document_processing_control(source, pdf_path)
    else:
        render_combined_embedding_control(sources, source["id"])
    render_delete_document_control(source)

    st.divider()
    render_pdf_upload()


def render_chat_header() -> None:
    st.title("TCM Citation RAG")
    st.caption("Ask a Traditional Chinese Medicine question and retrieve cited context.")

    if not rag_vectorstore_available():
        st.info(
            "No documents are currently available for retrieval. "
            "Open Document and upload a PDF before asking questions."
        )


def top_panel_options() -> list[str]:
    return ["chat", "documents"]


def top_panel_label(panel_id: str) -> str:
    return {
        "chat": "Chat",
        "documents": "Document",
    }[panel_id]


def render_top_panel() -> None:
    pending_panel = st.session_state.get("pending_top_panel_selection")

    if pending_panel in top_panel_options():
        st.session_state.active_top_panel = pending_panel
        st.session_state.top_panel_selection = pending_panel
        st.session_state.pending_top_panel_selection = None

    with st.container(border=True):
        selected_panel = st.segmented_control(
            "Main navigation",
            top_panel_options(),
            format_func=top_panel_label,
            key="top_panel_selection",
            label_visibility="collapsed",
            width="stretch",
        )

    if selected_panel and selected_panel != st.session_state.active_top_panel:
        st.session_state.active_top_panel = selected_panel


def document_window_items() -> list[dict]:
    return [{"id": "documents", "title": "Documents", "type": "documents"}] + list(
        st.session_state.app_windows
    )


def active_document_window() -> dict:
    windows = document_window_items()

    for window in windows:
        if window["id"] == st.session_state.active_document_window_id:
            return window

    st.session_state.active_document_window_id = "documents"
    return windows[0]


def document_window_label(window_id: str) -> str:
    for window in document_window_items():
        if window["id"] == window_id:
            return window["title"]

    return "Documents"


def render_document_window_bar() -> None:
    windows = document_window_items()

    if len(windows) <= 1:
        return

    active_id = active_document_window()["id"]
    column_widths = []

    for index, window in enumerate(windows):
        if window["id"] == "documents":
            column_widths.append(2.2)
        else:
            column_widths.extend([4.2, 0.55])

        if index < len(windows) - 1:
            column_widths.append(0.25)

    with st.container(
        key="doc_window_panel",
    ):
        columns = st.columns(column_widths, gap=None, vertical_alignment="center")
        column_index = 0

        for window in windows:
            window_id = window["id"]
            key_suffix = re.sub(r"[^a-zA-Z0-9_]+", "_", window_id)

            if window_id == "documents":
                with columns[column_index]:
                    if st.button(
                        window["title"],
                        key=f"select_window_single_{key_suffix}",
                        type="primary" if window_id == active_id else "secondary",
                        use_container_width=True,
                    ):
                        st.session_state.active_document_window_id = window_id
                        st.rerun()

                column_index += 1
            else:
                button_type = "primary" if window_id == active_id else "secondary"

                with columns[column_index]:
                    if st.button(
                        window["title"],
                        key=f"select_window_close_{key_suffix}",
                        type=button_type,
                        use_container_width=True,
                    ):
                        source_id = str(window.get("source_id") or "").strip()
                        if source_id:
                            request_selected_source(source_id)
                        st.session_state.active_document_window_id = window_id
                        st.rerun()

                column_index += 1

                with columns[column_index]:
                    st.button(
                        "X",
                        key=f"close_window_{key_suffix}",
                        help=f"Close {window['title']}",
                        type=button_type,
                        on_click=close_window,
                        args=(window_id,),
                        use_container_width=True,
                    )

                column_index += 1

            if column_index < len(columns):
                column_index += 1


def render_chunks_window(window: dict) -> None:
    source = source_for_id(str(window.get("source_id") or ""))

    if source is None:
        st.title("Chunk texts")
        st.error("The selected source could not be found.")
        return

    chunks = load_source_chunks(source["chunks_path"])
    st.title(f"{source['display_name']} chunk texts")
    st.caption(f"Chunks: `{len(chunks)}`")

    st.text_area(
        "Chunk texts",
        value=format_chunk_texts(chunks),
        height=650,
        disabled=True,
    )


def render_pdf_window(window: dict) -> None:
    source = source_for_id(str(window.get("source_id") or ""))

    if source is None:
        st.title("PDF")
        st.error("The selected source could not be found.")
        return

    pdf_path = local_pdf_path(source)
    st.title(f"{source['display_name']} PDF")

    if pdf_path is None:
        st.info("No PDF file found for this document.")
        return

    try:
        page_count = pdf_page_count(str(pdf_path))
    except Exception as exc:
        st.error("Could not open this PDF.")
        st.exception(exc)
        return

    page_key = f"pdf_page_{source['id']}"
    st.session_state[page_key] = min(
        max(int(st.session_state.get(page_key, 1)), 1),
        page_count,
    )

    page_controls_key = re.sub(r"[^a-zA-Z0-9_]+", "_", source["id"])
    with st.container(key=f"pdf_page_controls_{page_controls_key}"):
        page_controls = st.columns(
            [1.55, 1.15, 2.1, 5.2],
            gap="small",
            vertical_alignment="center",
        )
        with page_controls[0]:
            if st.button(
                "Previous",
                key=f"previous_pdf_page_{page_controls_key}",
                disabled=st.session_state[page_key] <= 1,
                use_container_width=True,
            ):
                st.session_state[page_key] -= 1
                st.rerun()

        with page_controls[1]:
            if st.button(
                "Next",
                key=f"next_pdf_page_{page_controls_key}",
                disabled=st.session_state[page_key] >= page_count,
                use_container_width=True,
            ):
                st.session_state[page_key] += 1
                st.rerun()

        with page_controls[2]:
            st.number_input(
                "Page",
                min_value=1,
                max_value=page_count,
                step=1,
                key=page_key,
                label_visibility="collapsed",
            )

    st.caption(f"Page `{st.session_state[page_key]}` of `{page_count}`")

    try:
        page_image = render_pdf_page_image(str(pdf_path), int(st.session_state[page_key]))
    except Exception as exc:
        st.error("Could not render this PDF page.")
        st.exception(exc)
        return

    st.image(page_image, width="stretch")


def render_document_panel() -> None:
    sync_document_window_state()
    render_document_window_bar()
    window = active_document_window()

    if window["type"] == "documents":
        render_document_window()
        return

    if window["type"] == "chunks":
        render_chunks_window(window)
        return

    if window["type"] == "pdf":
        render_pdf_window(window)
        return


def render_active_panel() -> None:
    if st.session_state.active_top_panel == "documents":
        render_document_panel()
        return

    render_chat_header()
    replay_chat_history()
    handle_user_question()


def save_current_chat() -> dict | None:
    saved_chat = save_chat_session(
        list(st.session_state.messages),
        st.session_state.current_chat_id,
    )

    if saved_chat is None:
        return None

    st.session_state.current_chat_id = saved_chat["id"]
    st.session_state.current_chat_title = saved_chat["title"]
    st.session_state.messages = saved_chat["messages"]

    return saved_chat


def load_chat_session(chat_id: str) -> None:
    session = read_chat_file(chat_file_path(chat_id))

    if session is None:
        st.warning("That saved chat could not be loaded.")
        return

    st.session_state.current_chat_id = session["id"]
    st.session_state.current_chat_title = session["title"]
    st.session_state.messages = session["messages"]
    request_top_panel("chat")
    st.rerun()


def start_new_chat() -> None:
    save_current_chat()
    st.session_state.messages = []
    st.session_state.current_chat_id = None
    st.session_state.current_chat_title = "Unsaved chat"
    request_top_panel("chat")
    st.rerun()


def render_sidebar() -> None:
    with st.sidebar:
        st.header("Status")
        render_active_jobs_panel()
        combined_manifest = load_combined_embedding_manifest()
        if combined_manifest:
            render_combined_embedding_status()
        else:
            st.write(f"Vector store: `{current_vectorstore_label()}`")
        st.slider(
            "threshold",
            min_value=MIN_MAX_DISTANCE,
            max_value=MAX_MAX_DISTANCE,
            step=0.05,
            key="max_distance",
            on_change=save_app_settings,
            help=(
                "Threshold 越高，RAG 越容易將文件判定為相關；"
                "Threshold 越低，則判定標準越嚴格。如果 RAG 經常回答"
                "與問題無關的內容，可以適當降低 Threshold；反之，如果 RAG "
                "無法回答與中醫（TCM）相關的問題，則可以適當提高 Threshold，"
                "以增加檢索到相關資料的機會。"
            ),
        )

        st.divider()
        st.header("Chats")
        st.caption(f"Current: {st.session_state.current_chat_title}")
        chat_busy = chat_job_in_progress()

        if st.button("New chat", use_container_width=True, disabled=chat_busy):
            start_new_chat()

        sessions = load_chat_sessions()

        if sessions:
            session_by_id = {session["id"]: session for session in sessions}
            session_ids = list(session_by_id)
            current_chat_id = st.session_state.current_chat_id
            selected_index = 0

            if current_chat_id in session_by_id:
                selected_index = session_ids.index(current_chat_id)

            selected_chat_id = st.selectbox(
                "Saved chats",
                session_ids,
                index=selected_index,
                format_func=lambda chat_id: session_label(session_by_id[chat_id]),
            )

            if st.button("Open selected chat", use_container_width=True, disabled=chat_busy):
                if selected_chat_id != st.session_state.current_chat_id:
                    save_current_chat()

                load_chat_session(selected_chat_id)
        else:
            st.info("No saved chats yet.")

        st.caption("Educational demo only. Not medical advice.")


def replay_chat_history() -> None:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            render_chat_message(message)


def install_ime_safe_enter_submit() -> None:
    st.html(
        """
        <script>
        (() => {
            const attachImeSafeEnter = () => {
                const doc = window.parent.document;
                const forms = Array.from(doc.querySelectorAll('div[data-testid="stForm"]'));
                const form = forms[forms.length - 1];

                if (!form) return;

                const input = form.querySelector('textarea, input[type="text"]');
                const button = form.querySelector('button');

                if (!input || !button || input.dataset.imeSafeEnterInstalled === "true") {
                    return;
                }

                input.dataset.imeSafeEnterInstalled = "true";
                let composing = false;

                input.addEventListener("compositionstart", () => {
                    composing = true;
                });

                input.addEventListener("compositionend", () => {
                    setTimeout(() => {
                        composing = false;
                    }, 0);
                });

                input.addEventListener("keydown", (event) => {
                    if (event.key !== "Enter") return;
                    if (event.shiftKey || event.ctrlKey || event.altKey || event.metaKey) return;
                    if (event.isComposing || composing || event.keyCode === 229) return;

                    event.preventDefault();
                    button.click();
                });
            };

            attachImeSafeEnter();

            const observer = new MutationObserver(attachImeSafeEnter);
            observer.observe(window.parent.document.body, {
                childList: true,
                subtree: true,
            });
        })();
        </script>
        """,
        unsafe_allow_javascript=True,
    )


def handle_user_question() -> None:
    vectorstore_ready = rag_vectorstore_available()
    chat_busy = chat_job_in_progress()
    with st.form("chat_input_form", clear_on_submit=True):
        input_column, send_column = st.columns([12, 1], vertical_alignment="bottom")

        with input_column:
            question = st.text_input(
                "Message",
                placeholder="Ask a TCM question...",
                label_visibility="collapsed",
            )

        with send_column:
            submitted = st.form_submit_button(
                "Send",
                type="primary",
                icon=":material/send:",
                help=(
                    "Send message"
                    if vectorstore_ready
                    else "Upload a document before asking questions."
                ),
                disabled=not vectorstore_ready or chat_busy,
                use_container_width=True,
            )

    install_ime_safe_enter_submit()

    if not submitted:
        return

    question = question.strip()
    if not question:
        st.warning("Please enter a question.")
        st.stop()

    chat_history = list(st.session_state.messages)
    user_message = {
        "role": "user",
        "content": question,
    }
    st.session_state.messages.append(user_message)
    with st.chat_message("user"):
        st.markdown(question)

    max_distance = clamp_max_distance(st.session_state.max_distance)
    st.session_state.max_distance = max_distance
    save_app_settings()

    with st.chat_message("assistant"):
        try:
            from tcmrag.rag import (
                prepare_tcm_answer,
                result_from_prepared_answer,
                stream_prepared_tcm_answer,
            )

            prepared_answer = prepare_tcm_answer(
                question,
                chat_history=chat_history,
                max_distance=max_distance,
            )
            if prepared_answer["ready_to_generate"]:
                answer = render_streamed_markdown(
                    stream_prepared_tcm_answer(prepared_answer)
                )
            else:
                answer = str(prepared_answer.get("answer") or "")
                st.markdown(renderable_markdown(answer))

            result = result_from_prepared_answer(prepared_answer, answer)
            assistant_message = assistant_message_from_rag_result(result)
            render_assistant_details(assistant_message)
        except Exception as exc:
            error_text = f"{type(exc).__name__}: {exc}"
            assistant_message = {
                "role": "assistant",
                "content": "The RAG pipeline failed to run.",
                "job_error": error_text,
            }
            st.error(assistant_message["content"])
            render_assistant_details(assistant_message)

    st.session_state.messages.append(assistant_message)
    save_current_chat()
    st.rerun()


sync_background_jobs()
handle_citation_navigation()
render_top_panel()
render_active_panel()
render_sidebar()
