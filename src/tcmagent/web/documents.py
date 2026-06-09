from __future__ import annotations

import json
import re
import shutil
import uuid
from hashlib import sha256
from pathlib import Path

import streamlit as st

from .config import DOC_SOURCES_DIR, now_iso


def read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(data, dict):
        return None

    return data


def load_document_sources() -> list[dict]:
    sources = []

    for manifest_path in sorted(DOC_SOURCES_DIR.glob("*/source.json")):
        metadata = read_json(manifest_path)
        if metadata is None:
            continue

        source_dir = manifest_path.parent
        source_id = str(metadata.get("id") or source_dir.name)
        chunks_path = source_dir / str(metadata.get("chunks_path") or "chunks.jsonl")
        original_filename = str(metadata.get("original_filename") or "")
        document_files = []

        if original_filename and (source_dir / original_filename).exists():
            document_files.append(original_filename)

        skipped_names = {"source.json", chunks_path.name, *document_files}
        for path in sorted(source_dir.iterdir()):
            if path.is_file() and path.name not in skipped_names:
                document_files.append(path.name)

        sources.append({
            "id": source_id,
            "display_name": str(metadata.get("display_name") or source_id),
            "source_dir": source_dir,
            "chunks_path": chunks_path,
            "document_files": document_files,
            "metadata": metadata,
        })

    return sources


def load_source_chunks(chunks_path: Path) -> list[dict]:
    chunks = []

    try:
        with chunks_path.open("r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue

                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if isinstance(chunk, dict):
                    chunks.append(chunk)
    except OSError:
        return []

    return chunks


def source_label(source: dict) -> str:
    return source["display_name"]


def is_uploaded_source(source: dict) -> bool:
    return str(source["metadata"].get("source_type") or "") == "uploaded_pdf"


def delete_document_source(source: dict) -> None:
    if not is_uploaded_source(source):
        raise ValueError("Only uploaded PDF sources can be deleted.")

    source_dir = Path(source["source_dir"]).resolve()
    docs_dir = DOC_SOURCES_DIR.resolve()

    if source_dir.parent != docs_dir:
        raise ValueError("Refusing to delete a source outside docs/sources.")

    if not (source_dir / "source.json").exists():
        raise ValueError("Refusing to delete a source without source.json.")

    if source_dir.exists():
        shutil.rmtree(source_dir)


def source_id_from_name(name: str) -> str:
    source_id = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return source_id or f"uploaded_pdf_{uuid.uuid4().hex[:8]}"


def unique_source_dir(source_id: str) -> tuple[str, Path]:
    candidate_id = source_id
    counter = 2

    while (DOC_SOURCES_DIR / candidate_id).exists():
        candidate_id = f"{source_id}_{counter}"
        counter += 1

    return candidate_id, DOC_SOURCES_DIR / candidate_id


def existing_source_for_uploaded_pdf(original_filename: str, file_hash: str) -> dict | None:
    for source in load_document_sources():
        metadata = source["metadata"]
        source_dir = source["source_dir"]
        stored_filename = str(metadata.get("original_filename") or "")
        stored_file = source_dir / stored_filename

        if not stored_filename or not stored_file.exists():
            continue

        if str(metadata.get("file_sha256") or "") == file_hash:
            return metadata

        if stored_filename == original_filename:
            try:
                stored_hash = sha256(stored_file.read_bytes()).hexdigest()
            except OSError:
                continue

            if stored_hash == file_hash:
                return metadata

    return None


def save_uploaded_pdf(uploaded_pdf) -> dict:
    original_filename = Path(uploaded_pdf.name).name
    file_bytes = uploaded_pdf.getvalue()

    if not original_filename.lower().endswith(".pdf"):
        raise ValueError("Only PDF files can be uploaded.")

    if not file_bytes.lstrip().startswith(b"%PDF"):
        raise ValueError("The uploaded file does not look like a valid PDF.")

    file_hash = sha256(file_bytes).hexdigest()
    existing_source = existing_source_for_uploaded_pdf(original_filename, file_hash)

    if existing_source is not None:
        return existing_source

    display_name = Path(original_filename).stem or "Uploaded PDF"
    source_id, source_dir = unique_source_dir(source_id_from_name(display_name))
    source_dir.mkdir(parents=True, exist_ok=False)

    pdf_path = source_dir / original_filename
    pdf_path.write_bytes(file_bytes)

    metadata = {
        "id": source_id,
        "display_name": display_name,
        "original_filename": original_filename,
        "chunks_path": "chunks.jsonl",
        "source_type": "uploaded_pdf",
        "file_sha256": file_hash,
        "created_at": now_iso(),
    }
    (source_dir / "source.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return metadata


def chunks_window_id(source_id: str) -> str:
    return f"chunks:{source_id}"


def pdf_window_id(source_id: str) -> str:
    return f"pdf:{source_id}"


def local_pdf_path(source: dict) -> Path | None:
    source_dir = source["source_dir"]
    metadata = source["metadata"]
    filenames = []
    original_filename = str(metadata.get("original_filename") or "")

    if original_filename:
        filenames.append(original_filename)

    filenames.extend(source["document_files"])

    for filename in filenames:
        path = source_dir / filename
        if path.exists() and path.suffix.lower() == ".pdf":
            return path

    for path in sorted(source_dir.glob("*.pdf")):
        return path

    return None


@st.cache_data(show_spinner=False)
def pdf_page_count(pdf_path_text: str) -> int:
    import fitz

    with fitz.open(pdf_path_text) as document:
        return document.page_count


@st.cache_data(show_spinner=False)
def render_pdf_page_image(pdf_path_text: str, page_number: int) -> bytes:
    import fitz

    with fitz.open(pdf_path_text) as document:
        page_index = min(max(page_number, 1), document.page_count) - 1
        page = document.load_page(page_index)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(1.7, 1.7), alpha=False)
        return pixmap.tobytes("png")


def source_for_id(source_id: str) -> dict | None:
    for source in load_document_sources():
        if source["id"] == source_id:
            return source

    return None


def format_chunk_texts(chunks: list[dict]) -> str:
    chunk_texts = []

    for index, chunk in enumerate(chunks, start=1):
        text = str(chunk.get("text") or "").strip()

        if text:
            chunk_texts.append(f"Chunk {index}\n{text}")

    return "\n\n---\n\n".join(chunk_texts)
