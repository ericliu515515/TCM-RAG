from __future__ import annotations

import copy
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Lock
from typing import Any, Callable


BackgroundProgressCallback = Callable[[dict[str, Any]], None]

ACTIVE_JOB_STATUSES = {"queued", "running"}
TERMINAL_JOB_STATUSES = {"completed", "failed"}

_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tcmrag_bg")
_JOBS: dict[str, dict[str, Any]] = {}
_LOCK = Lock()


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def submit_background_job(
    *,
    kind: str,
    label: str,
    target: Callable[..., Any],
    args: tuple[Any, ...] = (),
    kwargs: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    progress_kwarg: str | None = None,
) -> str:
    job_id = uuid.uuid4().hex
    record = {
        "id": job_id,
        "kind": str(kind),
        "label": str(label),
        "status": "queued",
        "progress": 0.0,
        "message": str(label),
        "feedback": "",
        "feedback_title": "",
        "result": None,
        "error": "",
        "exception_type": "",
        "traceback": "",
        "metadata": dict(metadata or {}),
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "started_at": None,
        "finished_at": None,
    }
    with _LOCK:
        _JOBS[job_id] = record

    call_kwargs = dict(kwargs or {})
    if progress_kwarg:
        call_kwargs[progress_kwarg] = make_progress_callback(job_id)

    def runner() -> None:
        update_background_job(
            job_id,
            status="running",
            progress=0.01,
            message=str(label),
            started_at=now_iso(),
        )
        try:
            result = target(*args, **call_kwargs)
        except Exception as exc:
            update_background_job(
                job_id,
                status="failed",
                progress=1.0,
                message=f"{label} failed.",
                error=str(exc),
                exception_type=type(exc).__name__,
                traceback=traceback.format_exc(),
                finished_at=now_iso(),
            )
            return

        update_background_job(
            job_id,
            status="completed",
            progress=1.0,
            message=f"{label} finished.",
            result=result,
            finished_at=now_iso(),
        )

    _EXECUTOR.submit(runner)
    return job_id


def make_progress_callback(job_id: str) -> BackgroundProgressCallback:
    def update(event: dict[str, Any]) -> None:
        update_background_job(
            job_id,
            progress=event.get("progress"),
            message=event.get("message"),
            feedback=event.get("feedback"),
            feedback_title=event.get("feedback_title"),
            metadata_updates={
                "attempt": event.get("attempt"),
                "max_attempts": event.get("max_attempts"),
                "stage": event.get("stage"),
                "run_id": event.get("run_id"),
            },
        )

    return update


def update_background_job(
    job_id: str,
    *,
    status: str | None = None,
    progress: float | int | None = None,
    message: str | None = None,
    feedback: str | None = None,
    feedback_title: str | None = None,
    result: Any = None,
    error: str | None = None,
    exception_type: str | None = None,
    traceback: str | None = None,
    metadata_updates: dict[str, Any] | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
) -> None:
    with _LOCK:
        record = _JOBS.get(job_id)
        if record is None:
            return

        if status is not None:
            record["status"] = str(status)
        if progress is not None:
            try:
                record["progress"] = max(0.0, min(float(progress), 1.0))
            except (TypeError, ValueError):
                pass
        if message is not None:
            record["message"] = str(message)
        if feedback is not None:
            record["feedback"] = str(feedback)
        if feedback_title is not None:
            record["feedback_title"] = str(feedback_title)
        if result is not None:
            record["result"] = result
        if error is not None:
            record["error"] = str(error)
        if exception_type is not None:
            record["exception_type"] = str(exception_type)
        if traceback is not None:
            record["traceback"] = str(traceback)
        if started_at is not None:
            record["started_at"] = str(started_at)
        if finished_at is not None:
            record["finished_at"] = str(finished_at)
        if metadata_updates:
            record_metadata = record.get("metadata")
            if not isinstance(record_metadata, dict):
                record_metadata = {}
                record["metadata"] = record_metadata
            for key, value in metadata_updates.items():
                if value is None:
                    continue
                record_metadata[key] = value

        record["updated_at"] = now_iso()


def get_background_job_snapshot(job_id: str) -> dict[str, Any] | None:
    with _LOCK:
        record = _JOBS.get(job_id)
        if record is None:
            return None
        return copy.deepcopy(record)


def get_background_job_snapshots(job_ids: list[str]) -> list[dict[str, Any]]:
    snapshots = []
    for job_id in job_ids:
        snapshot = get_background_job_snapshot(job_id)
        if snapshot is not None:
            snapshots.append(snapshot)
    return snapshots


def discard_background_job(job_id: str) -> None:
    with _LOCK:
        _JOBS.pop(job_id, None)


def is_background_job_active(job: dict[str, Any] | None) -> bool:
    if not isinstance(job, dict):
        return False
    return str(job.get("status") or "") in ACTIVE_JOB_STATUSES

