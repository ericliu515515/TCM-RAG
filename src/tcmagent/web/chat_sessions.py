from __future__ import annotations

import json
import uuid
from pathlib import Path

from .config import CHAT_SESSIONS_DIR, clamp_max_distance, now_iso


def chat_file_path(chat_id: str) -> Path:
    return CHAT_SESSIONS_DIR / f"{chat_id}.json"


def clean_message(message: dict) -> dict:
    role = message.get("role")
    if role not in {"user", "assistant"}:
        role = "assistant"

    cleaned = {
        "role": role,
        "content": str(message.get("content", "")),
    }

    if role == "assistant":
        cleaned["sources"] = message.get("sources", [])
        cleaned["scores"] = message.get("scores", [])

        search_question = message.get("search_question")
        if search_question:
            cleaned["search_question"] = str(search_question)

        max_distance = message.get("max_distance")
        if max_distance is not None:
            cleaned["max_distance"] = clamp_max_distance(max_distance)

    return cleaned


def clean_messages(messages: list[dict]) -> list[dict]:
    cleaned_messages = []

    for message in messages:
        if isinstance(message, dict):
            cleaned_messages.append(clean_message(message))

    return cleaned_messages


def chat_title_from_messages(messages: list[dict]) -> str:
    for message in messages:
        if message.get("role") != "user":
            continue

        title = " ".join(str(message.get("content", "")).split())
        if not title:
            continue

        if len(title) > 42:
            return f"{title[:39]}..."

        return title

    return "Untitled chat"


def read_chat_file(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(data, dict):
        return None

    messages = data.get("messages", [])
    if not isinstance(messages, list):
        messages = []

    clean_stored_messages = clean_messages(messages)
    title = str(data.get("title") or chat_title_from_messages(clean_stored_messages))

    return {
        "id": str(data.get("id") or path.stem),
        "title": title,
        "created_at": str(data.get("created_at") or now_iso()),
        "updated_at": str(data.get("updated_at") or data.get("created_at") or now_iso()),
        "messages": clean_stored_messages,
    }


def save_chat_session(messages: list[dict], chat_id: str | None = None) -> dict | None:
    clean_stored_messages = clean_messages(messages)

    if not clean_stored_messages:
        return None

    saved_chat_id = chat_id or uuid.uuid4().hex
    path = chat_file_path(saved_chat_id)
    existing_chat = read_chat_file(path) if path.exists() else None
    created_at = existing_chat["created_at"] if existing_chat else now_iso()
    title = chat_title_from_messages(clean_stored_messages)
    payload = {
        "id": saved_chat_id,
        "title": title,
        "created_at": created_at,
        "updated_at": now_iso(),
        "messages": clean_stored_messages,
    }

    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    return payload


def load_chat_sessions() -> list[dict]:
    sessions = []

    for path in CHAT_SESSIONS_DIR.glob("*.json"):
        session = read_chat_file(path)
        if session is not None:
            sessions.append(session)

    return sorted(sessions, key=lambda session: session["updated_at"], reverse=True)


def session_label(session: dict) -> str:
    updated_at = session.get("updated_at", "").replace("T", " ")

    if updated_at:
        return f"{session['title']} - {updated_at}"

    return session["title"]
