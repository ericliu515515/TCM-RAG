from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_DIR = PROJECT_ROOT / "src"
CHAT_SESSIONS_DIR = PROJECT_ROOT / "docs" / "chat_sessions"
DOC_SOURCES_DIR = PROJECT_ROOT / "docs" / "sources"
APP_SETTINGS_PATH = PROJECT_ROOT / "docs" / "app_settings.json"
DEFAULT_VECTORSTORE_LABEL = (
    "docs/sources/tcm_basic_theory/vectorstores/faiss_openai_test_embedding_3_small"
)
DEFAULT_MAX_DISTANCE = 1.3
MIN_MAX_DISTANCE = 1.0
MAX_MAX_DISTANCE = 1.5


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def ensure_app_environment() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    CHAT_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    DOC_SOURCES_DIR.mkdir(parents=True, exist_ok=True)


def clamp_max_distance(value) -> float:
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return DEFAULT_MAX_DISTANCE

    return min(max(numeric_value, MIN_MAX_DISTANCE), MAX_MAX_DISTANCE)


def load_app_settings() -> dict:
    try:
        data = json.loads(APP_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"max_distance": DEFAULT_MAX_DISTANCE}

    if not isinstance(data, dict):
        return {"max_distance": DEFAULT_MAX_DISTANCE}

    return {
        "max_distance": clamp_max_distance(data.get("max_distance", DEFAULT_MAX_DISTANCE))
    }


def write_app_settings(max_distance: float) -> None:
    payload = {
        "max_distance": clamp_max_distance(max_distance),
        "updated_at": now_iso(),
    }
    APP_SETTINGS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
