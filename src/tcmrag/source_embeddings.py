from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings


PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMBINED_VECTORSTORE_DIR = (
    PROJECT_ROOT / "docs" / "vectorstores" / "faiss_openai_text_embedding_3_small_combined"
)
COMBINED_MANIFEST_PATH = COMBINED_VECTORSTORE_DIR / "manifest.json"
EMBEDDING_MODEL_NAME = "text-embedding-3-small"
VECTORSTORE_KEY = "openai_text_embedding_3_small"
VECTORSTORE_DIRNAME = "faiss_openai_text_embedding_3_small"
EVALUATION_TOP_K = 5

GOOD_QUESTIONS = [
    "中醫如何理解陰陽失衡造成的疾病？",
    "脾胃在中醫理論中負責哪些生理功能？",
    "什麼是氣血津液，彼此之間有什麼關係？",
    "中醫所說的六淫包含哪些外感病因？",
    "肝鬱氣滯在臨床上可能出現哪些表現？",
    "腎精不足會如何影響人體生長與發育？",
    "飲食不節為什麼會損傷脾胃？",
    "望聞問切四診分別觀察哪些內容？",
    "痰飲在中醫病因病機中如何形成？",
    "寒熱虛實如何用來辨別證候？",
]

BAD_QUESTIONS = [
    "現任美國總統是誰？",
    "台積電股價今天多少？",
    "如何用 Python 讀取 CSV 檔案？",
    "台北明天的天氣預報是什麼？",
    "NBA 總冠軍賽最新比分是多少？",
    "如何規劃東京五天四夜自由行？",
    "披薩麵團需要發酵多久？",
    "第二次世界大戰是哪一年結束的？",
    "如何計算複利投資報酬率？",
    "哪一款筆電適合剪輯 4K 影片？",
]


def run_embedding_for_source(source: dict, embedding_model=None) -> dict:
    chunks = read_chunks(source["chunks_path"])
    if not chunks:
        raise ValueError("No chunks found. Generate chunks before embedding.")

    documents = chunks_to_documents(chunks, source)
    if embedding_model is None:
        embedding_model = OpenAIEmbeddings(model=EMBEDDING_MODEL_NAME)

    vectorstore = FAISS.from_documents(documents, embedding_model)
    source_dir = Path(source["source_dir"])
    vectorstore_dir = source_dir / "vectorstores" / VECTORSTORE_DIRNAME
    vectorstore_dir.mkdir(parents=True, exist_ok=True)
    vectorstore.save_local(str(vectorstore_dir))

    evaluation = evaluate_vectorstore(vectorstore)
    result = {
        "status": "embedded",
        "model": EMBEDDING_MODEL_NAME,
        "vectorstore_key": VECTORSTORE_KEY,
        "vectorstore_path": str(vectorstore_dir.relative_to(source_dir)),
        "chunk_count": len(documents),
        "evaluation": evaluation,
        "updated_at": now_iso(),
    }
    update_embedding_manifest(source_dir, result)
    return result


def run_combined_embedding_for_sources(
    sources: list[dict],
    embedding_model=None,
) -> dict:
    source_documents = []
    source_summaries = []

    for source in sources:
        chunks_path = Path(source["chunks_path"])
        if not chunks_path.exists():
            continue

        chunks = read_chunks(chunks_path)
        documents = chunks_to_documents(chunks, source)
        if not documents:
            continue

        source_documents.extend(documents)
        source_summaries.append({
            "id": source["id"],
            "display_name": source["display_name"],
            "chunk_count": len(documents),
        })

    if not source_documents:
        raise ValueError("No chunked sources found. Generate chunks before embedding.")

    if embedding_model is None:
        embedding_model = OpenAIEmbeddings(model=EMBEDDING_MODEL_NAME)

    vectorstore = FAISS.from_documents(source_documents, embedding_model)
    COMBINED_VECTORSTORE_DIR.mkdir(parents=True, exist_ok=True)
    vectorstore.save_local(str(COMBINED_VECTORSTORE_DIR))

    evaluation = evaluate_vectorstore(vectorstore)
    result = {
        "status": "embedded",
        "model": EMBEDDING_MODEL_NAME,
        "vectorstore_key": "combined_openai_text_embedding_3_small",
        "vectorstore_path": display_path(COMBINED_VECTORSTORE_DIR),
        "source_count": len(source_summaries),
        "sources": source_summaries,
        "chunk_count": len(source_documents),
        "evaluation": evaluation,
        "updated_at": now_iso(),
    }
    write_combined_manifest(result)
    return result


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def load_combined_embedding_manifest() -> dict | None:
    try:
        data = json.loads(COMBINED_MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if isinstance(data, dict):
        return data

    return None


def clear_combined_vectorstore() -> None:
    if COMBINED_VECTORSTORE_DIR.exists():
        shutil.rmtree(COMBINED_VECTORSTORE_DIR)


def combined_manifest_source_ids() -> set[str]:
    manifest = load_combined_embedding_manifest()
    if not isinstance(manifest, dict):
        return set()

    sources = manifest.get("sources")
    if not isinstance(sources, list):
        return set()

    source_ids = set()
    for source in sources:
        if not isinstance(source, dict):
            continue

        source_id = str(source.get("id") or "").strip()
        if source_id:
            source_ids.add(source_id)

    return source_ids


def combined_vectorstore_ready() -> bool:
    return (
        (COMBINED_VECTORSTORE_DIR / "index.faiss").exists()
        and (COMBINED_VECTORSTORE_DIR / "index.pkl").exists()
    )


def read_chunks(chunks_path: Path) -> list[dict[str, Any]]:
    chunks = []

    with Path(chunks_path).open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                chunk = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid chunks JSONL at line {line_number}: {exc}") from exc

            if not isinstance(chunk, dict):
                raise ValueError(f"Chunk line {line_number} is not a JSON object.")

            chunks.append(chunk)

    return chunks


def chunks_to_documents(
    chunks: list[dict[str, Any]],
    source: dict | None = None,
) -> list[Document]:
    documents = []

    for index, chunk in enumerate(chunks, start=1):
        text = str(chunk.get("text") or "").strip()
        if not text:
            continue

        metadata = {
            key: value
            for key, value in chunk.items()
            if key != "text"
        }
        metadata.setdefault("chunk_index", index)
        if source is not None:
            metadata.setdefault("source_id", source["id"])
            metadata.setdefault("source_display_name", source["display_name"])
            source_metadata = source.get("metadata") or {}
            metadata.setdefault(
                "source_type",
                source.get("source_type")
                or source_metadata.get("source_type")
                or "built_in",
            )
        documents.append(Document(page_content=text, metadata=metadata))

    if not documents:
        raise ValueError("Chunks exist, but none contain text.")

    return documents


def evaluate_vectorstore(vectorstore) -> dict:
    good = evaluate_questions(vectorstore, GOOD_QUESTIONS)
    bad = evaluate_questions(vectorstore, BAD_QUESTIONS)

    return {
        "top_k": EVALUATION_TOP_K,
        "good_questions_count": len(GOOD_QUESTIONS),
        "bad_questions_count": len(BAD_QUESTIONS),
        "good_avg_top_k_distance": good["average_distance"],
        "bad_avg_top_k_distance": bad["average_distance"],
        "good_questions": GOOD_QUESTIONS,
        "bad_questions": BAD_QUESTIONS,
    }


def evaluate_questions(vectorstore, questions: list[str]) -> dict:
    distances = []

    for question in questions:
        results = vectorstore.similarity_search_with_score(question, k=EVALUATION_TOP_K)
        distances.extend(float(score) for _, score in results)

    average_distance = (
        round(sum(distances) / len(distances), 6)
        if distances
        else None
    )

    return {
        "average_distance": average_distance,
        "distance_count": len(distances),
    }


def update_embedding_manifest(source_dir: Path, result: dict) -> None:
    manifest_path = source_dir / "source.json"
    metadata = json.loads(manifest_path.read_text(encoding="utf-8"))
    vectorstores = metadata.get("vectorstores")
    if not isinstance(vectorstores, dict):
        vectorstores = {}

    vectorstores[VECTORSTORE_KEY] = result["vectorstore_path"]
    metadata["vectorstores"] = vectorstores
    metadata["embedding"] = result
    manifest_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def write_combined_manifest(result: dict) -> None:
    COMBINED_MANIFEST_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
