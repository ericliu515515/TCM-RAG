from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tcmrag.chunk import make_chunk_id, make_citation_markdown, make_citation_url


MAX_CHUNK_CHARS = 2200
SHORT_CHUNK_CHARS = 10
MAX_SHORT_CHUNK_RATIO = 0.10
MIN_SOURCE_MATCH_RATIO = 0.45


def write_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    records = []

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at line {line_number}: {exc}") from exc

            if not isinstance(value, dict):
                raise ValueError(f"JSONL line {line_number} is not an object.")

            records.append(value)

    return records


def validate_candidate_chunks(
    raw_chunks: list[dict],
    pages: list[dict[str, Any]],
    source_id: str,
    display_name: str,
    source_url: str,
) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    normalized_chunks: list[dict] = []
    page_texts = build_page_texts(pages)
    valid_pages = set(page_texts)

    if not raw_chunks:
        errors.append("The chunker produced no chunks.")

    chunk_counts_by_start_page: dict[int, int] = {}
    source_match_ratios = []
    chunk_lengths = []
    short_chunk_count = 0

    for index, raw_chunk in enumerate(raw_chunks, start=1):
        normalized = normalize_raw_chunk(
            raw_chunk,
            index,
            source_id,
            display_name,
            source_url,
            valid_pages,
            chunk_counts_by_start_page,
            errors,
            warnings,
        )
        if normalized is None:
            continue

        text = normalized["text"]
        chunk_length = len(text)
        chunk_lengths.append(chunk_length)
        if chunk_length < SHORT_CHUNK_CHARS:
            short_chunk_count += 1
        page_text = "\n".join(page_texts[pdf_page] for pdf_page in normalized["pdf_pages"])
        source_match_ratio = estimate_source_match_ratio(text, page_text)
        source_match_ratios.append(source_match_ratio)

        if source_match_ratio < MIN_SOURCE_MATCH_RATIO:
            warnings.append(
                f"{normalized['chunk_id']} has low source-text match "
                f"({source_match_ratio:.2f})."
            )

        normalized["source_match_ratio"] = round(source_match_ratio, 3)
        normalized_chunks.append(normalized)

    stats = build_stats(
        normalized_chunks,
        chunk_lengths,
        short_chunk_count,
        source_match_ratios,
        page_texts,
    )

    if normalized_chunks:
        average_match = stats["source_match_ratio_avg"]
        if average_match < MIN_SOURCE_MATCH_RATIO:
            errors.append(
                f"Average source-text match is too low ({average_match:.2f})."
            )

        referenced_ratio = stats["referenced_source_chars_ratio"]
        if referenced_ratio < 0.8:
            warnings.append(
                "Chunks reference pages covering only "
                f"{referenced_ratio:.2f} of extracted source text."
            )

        chunk_to_source_ratio = stats["chunk_to_source_chars_ratio"]
        if chunk_to_source_ratio < 0.5:
            warnings.append(
                "Chunk text is much shorter than extracted source text "
                f"({chunk_to_source_ratio:.2f} chunk/source char ratio)."
            )

        short_chunk_ratio = stats["short_chunk_ratio"]
        if short_chunk_ratio > MAX_SHORT_CHUNK_RATIO:
            errors.append(
                "Too many chunks are shorter than "
                f"{SHORT_CHUNK_CHARS} chars "
                f"({stats['short_chunk_count']} / {stats['chunk_count']} = {short_chunk_ratio:.2f})."
            )
        elif stats["short_chunk_count"] > 0:
            warnings.append(
                "Some chunks are very short, but still within the allowed limit "
                f"({stats['short_chunk_count']} / {stats['chunk_count']} under {SHORT_CHUNK_CHARS} chars)."
            )

    return {
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "stats": stats,
        "chunks": normalized_chunks,
    }


def normalize_raw_chunk(
    raw_chunk: dict,
    index: int,
    source_id: str,
    display_name: str,
    source_url: str,
    valid_pages: set[int],
    chunk_counts_by_start_page: dict[int, int],
    errors: list[str],
    warnings: list[str],
) -> dict | None:
    text = str(raw_chunk.get("text") or "").strip()
    if not text:
        errors.append(f"Chunk {index} has no text.")
        return None

    pdf_pages = normalize_pdf_pages(raw_chunk)
    if not pdf_pages:
        errors.append(f"Chunk {index} has no valid pdf_pages.")
        return None

    invalid_pages = [pdf_page for pdf_page in pdf_pages if pdf_page not in valid_pages]
    if invalid_pages:
        errors.append(f"Chunk {index} references invalid pages: {invalid_pages}.")
        return None

    if len(text) > MAX_CHUNK_CHARS:
        errors.append(f"Chunk {index} is too long ({len(text)} chars).")
        return None

    start_page = pdf_pages[0]
    end_page = pdf_pages[-1]
    chunk_counts_by_start_page[start_page] = (
        chunk_counts_by_start_page.get(start_page, 0) + 1
    )
    chunk_index = chunk_counts_by_start_page[start_page]
    citation_link = make_citation_url(source_url, start_page)

    return {
        "chunk_id": str(raw_chunk.get("chunk_id") or make_chunk_id(start_page, end_page, chunk_index)),
        "text": text,
        "citation_link": citation_link,
        "pdf_page": start_page,
        "pdf_page_start": start_page,
        "pdf_page_end": end_page,
        "pdf_pages": pdf_pages,
        "citation_links": [make_citation_url(source_url, pdf_page) for pdf_page in pdf_pages],
        "citation_markdown": make_citation_markdown(display_name, source_url, pdf_pages),
        "source_id": source_id,
    }


def normalize_pdf_pages(raw_chunk: dict) -> list[int]:
    raw_pages = raw_chunk.get("pdf_pages")

    if raw_pages is None:
        raw_page = raw_chunk.get("pdf_page")
        raw_pages = [raw_page] if raw_page is not None else []

    if not isinstance(raw_pages, list):
        raw_pages = [raw_pages]

    pages = []
    for raw_page in raw_pages:
        try:
            page = int(raw_page)
        except (TypeError, ValueError):
            continue

        if page > 0 and page not in pages:
            pages.append(page)

    return sorted(pages)


def build_page_texts(pages: list[dict[str, Any]]) -> dict[int, str]:
    page_texts = {}

    for page in pages:
        try:
            pdf_page = int(page["pdf_page"])
        except (KeyError, TypeError, ValueError):
            continue

        page_texts[pdf_page] = str(page.get("text") or "")

    return page_texts


def build_stats(
    chunks: list[dict],
    chunk_lengths: list[int],
    short_chunk_count: int,
    source_match_ratios: list[float],
    page_texts: dict[int, str],
) -> dict:
    coverage_stats = build_source_coverage_stats(chunks, page_texts)

    if not chunks:
        return coverage_stats | {
            "chunk_count": 0,
            "chunk_chars_min": 0,
            "chunk_chars_avg": 0,
            "chunk_chars_max": 0,
            "short_chunk_count": 0,
            "short_chunk_ratio": 0,
            "source_match_ratio_min": 0,
            "source_match_ratio_avg": 0,
            "source_match_ratio_max": 0,
        }

    short_chunk_ratio = short_chunk_count / len(chunks)
    return coverage_stats | {
        "chunk_count": len(chunks),
        "chunk_chars_min": min(chunk_lengths),
        "chunk_chars_avg": round(sum(chunk_lengths) / len(chunk_lengths), 1),
        "chunk_chars_max": max(chunk_lengths),
        "short_chunk_count": short_chunk_count,
        "short_chunk_ratio": round(short_chunk_ratio, 3),
        "source_match_ratio_min": round(min(source_match_ratios), 3),
        "source_match_ratio_avg": round(
            sum(source_match_ratios) / len(source_match_ratios), 3
        ),
        "source_match_ratio_max": round(max(source_match_ratios), 3),
    }


def build_source_coverage_stats(chunks: list[dict], page_texts: dict[int, str]) -> dict:
    text_pages = {
        pdf_page: text
        for pdf_page, text in page_texts.items()
        if compact_text(text)
    }
    referenced_pages = sorted({
        pdf_page
        for chunk in chunks
        for pdf_page in chunk.get("pdf_pages", [])
        if pdf_page in text_pages
    })

    source_text_chars = sum(len(compact_text(text)) for text in text_pages.values())
    referenced_source_chars = sum(
        len(compact_text(text_pages[pdf_page]))
        for pdf_page in referenced_pages
    )
    chunk_text_chars = sum(
        len(compact_text(str(chunk.get("text") or "")))
        for chunk in chunks
    )

    if source_text_chars:
        referenced_source_chars_ratio = referenced_source_chars / source_text_chars
        chunk_to_source_chars_ratio = chunk_text_chars / source_text_chars
    else:
        referenced_source_chars_ratio = 0
        chunk_to_source_chars_ratio = 0

    return {
        "source_page_count": len(page_texts),
        "source_non_empty_page_count": len(text_pages),
        "source_text_chars": source_text_chars,
        "referenced_page_count": len(referenced_pages),
        "unreferenced_text_page_count": max(0, len(text_pages) - len(referenced_pages)),
        "referenced_source_chars": referenced_source_chars,
        "referenced_source_chars_ratio": round(referenced_source_chars_ratio, 3),
        "chunk_text_chars": chunk_text_chars,
        "chunk_to_source_chars_ratio": round(chunk_to_source_chars_ratio, 3),
    }


def estimate_source_match_ratio(chunk_text: str, page_text: str) -> float:
    chunk_compact = compact_text(chunk_text)
    page_compact = compact_text(page_text)

    if not chunk_compact:
        return 0.0
    if chunk_compact in page_compact:
        return 1.0

    sample_size = min(16, max(8, len(chunk_compact) // 8))
    samples = text_windows(chunk_compact, sample_size=sample_size, max_samples=24)
    if not samples:
        return 0.0

    hits = sum(1 for sample in samples if sample in page_compact)
    return hits / len(samples)


def text_windows(text: str, sample_size: int, max_samples: int) -> list[str]:
    if len(text) <= sample_size:
        return [text]

    step = max(1, (len(text) - sample_size) // max(max_samples - 1, 1))
    samples = []
    for start in range(0, len(text) - sample_size + 1, step):
        samples.append(text[start : start + sample_size])
        if len(samples) >= max_samples:
            break

    return samples


def compact_text(text: str) -> str:
    return re.sub(r"\s+", "", text)
