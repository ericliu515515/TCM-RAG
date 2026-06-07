"""Build page-aware RAG chunks from a PDF.

This module is intentionally small:

PDF -> pages -> chunks -> JSONL

It keeps PDF page numbers in each chunk so later RAG answers can cite the
original PDF with hyperlinks such as:

    https://example.com/book.pdf#page=23
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable


DEFAULT_SOURCE_URL = (
    "https://xiaojiang.byethost16.com/soft/"
    "%E7%94%B5%E5%AD%90%E4%B9%A6/"
    "%E4%B8%AD%E5%8C%BB%E5%9F%BA%E7%A1%80%E7%90%86%E8%AE%BA%EF%BC%88"
    "%E6%96%B0%E4%B8%96%E7%BA%AA%E7%AC%AC4%E7%89%88%EF%BC%89cnzyy.org.pdf?i=1"
)
DEFAULT_SKIP_FIRST_PAGES = 49
DEFAULT_CHUNK_SIZE = 600
SECTION_HEADING_MAX_CHARS = 40


NOISE_LINE_PATTERNS = [
    # Repeated cnzyy.org page watermark/header from the source PDF.
    r"^\s*琅嬛福地·中医药电子书\s+https?://cnzyy\.org\s+仅供学习和查询，请购买正版支持本书作者\s*$",
]

CHINESE_SECTION_NUMBER = r"[一二三四五六七八九十百千万〇零两]+"
ARABIC_SECTION_NUMBER = r"[0-9０-９]{1,2}"
SECTION_NUMBER = rf"(?:{CHINESE_SECTION_NUMBER}|{ARABIC_SECTION_NUMBER})"
BRACKETED_SECTION_MARKER = (
    rf"[（(﹙〔［\[\【]\s*{SECTION_NUMBER}\s*[）)﹚〕］\]\】]"
)
ORDERED_LIST_MARKER = rf"[0-9０-９]{{1,2}}[.．、]"
SECTION_START_PATTERN = re.compile(
    rf"^\s*(?:{BRACKETED_SECTION_MARKER}|{ORDERED_LIST_MARKER})"
)
BRACKETED_SECTION_START_PATTERN = re.compile(rf"^\s*{BRACKETED_SECTION_MARKER}")
ORDERED_LIST_START_PATTERN = re.compile(rf"^\s*{ORDERED_LIST_MARKER}")
LINE_SECTION_BREAK_PATTERN = re.compile(
    rf"(?m)\n\s*({BRACKETED_SECTION_MARKER}|{ORDERED_LIST_MARKER})"
)
INLINE_BRACKETED_SECTION_PATTERN = re.compile(
    rf"(?<=[。！？；;：:])\s*({BRACKETED_SECTION_MARKER})"
)
INLINE_ORDERED_LIST_PATTERN = re.compile(
    rf"(?<![\d０-９A-Za-z])\s*({ORDERED_LIST_MARKER})(?![\d０-９])"
)
STRUCTURAL_HEADING_START_PATTERN = re.compile(
    rf"^\s*(?:第.+?[章节篇]|[一二三四五六七八九十百千万〇零两]+、)"
)
CAPTION_OR_FRONT_MATTER_PATTERN = re.compile(r"^(?:[图表]\d|主要参考书目|参考书目|目录)$")
PHRASE_PUNCTUATION_PATTERN = re.compile(r"[，,。！？；;：:]")
SENTENCE_PUNCTUATION_PATTERN = re.compile(r"[。！？；;：:]")
TERMINAL_PUNCTUATION = "。！？.!?"
CLOSING_PUNCTUATION = "”’\"'）)】〕］》」』"


def normalize_text(text: str) -> str:
    """Clean extracted PDF text without changing its meaning."""
    text = text.replace("\u3000", " ")
    text = remove_noise_lines(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def remove_noise_lines(text: str) -> str:
    """Remove repeated PDF watermark/header lines that hurt retrieval."""
    for pattern in NOISE_LINE_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.MULTILINE)
    return text


def extract_pages(pdf_path: str | Path) -> list[dict[str, Any]]:
    """Extract text page by page.

    Returns:
        [
            {"pdf_page": 1, "text": "..."},
            {"pdf_page": 2, "text": "..."},
        ]

    The function tries three options:
    1. PyMuPDF, installed with: pip install pymupdf
    2. pypdf, installed with: pip install pypdf
    3. pdftotext command-line tool, if available on the system
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    pages = _extract_pages_with_pymupdf(pdf_path)
    if pages is not None:
        return pages

    pages = _extract_pages_with_pypdf(pdf_path)
    if pages is not None:
        return pages

    pages = _extract_pages_with_pdftotext(pdf_path)
    if pages is not None:
        return pages

    raise RuntimeError(
        "Could not extract PDF text. Install one extractor first, for example:\n"
        "  pip install pymupdf\n"
        "or:\n"
        "  pip install pypdf"
    )


def _extract_pages_with_pymupdf(pdf_path: Path) -> list[dict[str, Any]] | None:
    try:
        import fitz  # type: ignore[import-not-found]
    except ImportError:
        return None

    pages: list[dict[str, Any]] = []
    with fitz.open(pdf_path) as doc:
        for index, page in enumerate(doc, start=1):
            pages.append(
                {
                    "pdf_page": index,
                    "text": normalize_text(page.get_text("text")),
                }
            )
    return pages


def _extract_pages_with_pypdf(pdf_path: Path) -> list[dict[str, Any]] | None:
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]
    except ImportError:
        return None

    reader = PdfReader(str(pdf_path))
    pages: list[dict[str, Any]] = []
    for index, page in enumerate(reader.pages, start=1):
        pages.append(
            {
                "pdf_page": index,
                "text": normalize_text(page.extract_text() or ""),
            }
        )
    return pages


def _extract_pages_with_pdftotext(pdf_path: Path) -> list[dict[str, Any]] | None:
    try:
        subprocess.run(
            ["pdftotext", "-v"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except FileNotFoundError:
        return None

    with tempfile.TemporaryDirectory() as tmp_dir:
        output_path = Path(tmp_dir) / "book.txt"
        result = subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), str(output_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if result.returncode != 0 or not output_path.exists():
            return None

        # pdftotext separates pages with form-feed characters. A trailing
        # form-feed can create one extra empty split item, which is not a page.
        raw_pages = output_path.read_text(encoding="utf-8", errors="ignore").split("\f")
        if raw_pages and not raw_pages[-1].strip():
            raw_pages = raw_pages[:-1]

    pages = []
    for index, text in enumerate(raw_pages, start=1):
        pages.append({"pdf_page": index, "text": normalize_text(text)})
    return pages


def split_text(
    text: str, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = 80
) -> list[str]:
    """Split text into paragraph-based chunks.

    The PDF is still extracted page by page so every chunk can cite a page.
    Inside each page, this function splits on blank-line paragraphs, then merges
    nearby paragraphs until each chunk is close to chunk_size.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0:
        raise ValueError("overlap must be non-negative")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    paragraph_records = [
        {"text": paragraph, "pdf_pages": []} for paragraph in split_paragraphs(text)
    ]
    return [
        chunk["text"]
        for chunk in chunk_paragraph_records(
            paragraph_records,
            chunk_size=chunk_size,
            overlap=overlap,
        )
    ]


def is_section_start(text: str) -> bool:
    """Return True for subsection/list markers like （一）, (2), or 1."""
    return bool(SECTION_START_PATTERN.match(text))


def is_bracketed_section_start(text: str) -> bool:
    """Return True for markers like （一）, (2), ［三］, or 【4】."""
    return bool(BRACKETED_SECTION_START_PATTERN.match(text))


def is_ordered_list_start(text: str) -> bool:
    """Return True for markers like 1., 1．, or 1、."""
    return bool(ORDERED_LIST_START_PATTERN.match(text))


def split_paragraphs(text: str) -> list[str]:
    """Split normalized page text into cleaned paragraphs."""
    text = normalize_text(text)
    if not text:
        return []

    text = insert_section_breaks(text)
    raw_paragraphs = re.split(r"\n\s*\n", text)
    paragraphs = []
    for paragraph in raw_paragraphs:
        cleaned = _clean_paragraph(paragraph)
        if cleaned:
            paragraphs.append(cleaned)
    return paragraphs


def insert_section_breaks(text: str) -> str:
    """Add paragraph breaks before section markers glued by PDF extraction."""
    text = LINE_SECTION_BREAK_PATTERN.sub(r"\n\n\1", text)
    text = INLINE_BRACKETED_SECTION_PATTERN.sub(r"\n\n\1", text)
    text = INLINE_ORDERED_LIST_PATTERN.sub(r"\n\n\1", text)
    return text


def _clean_paragraph(paragraph: str) -> str:
    """Remove artificial PDF line wraps inside one paragraph."""
    lines = [line.strip() for line in paragraph.splitlines()]
    lines = [line for line in lines if line]
    return "".join(lines)


def _join_paragraphs(paragraphs: Iterable[str]) -> str:
    return "\n\n".join(paragraph.strip() for paragraph in paragraphs if paragraph.strip())


def build_paragraph_records(
    pages: Iterable[dict[str, Any]],
    skip_first_pages: int,
) -> list[dict[str, Any]]:
    """Build paragraph records, merging paragraphs split by page breaks."""
    records: list[dict[str, Any]] = []

    for page in pages:
        pdf_page = int(page["pdf_page"])
        if pdf_page <= skip_first_pages:
            continue

        paragraphs = split_paragraphs(str(page.get("text", "")))
        for index, paragraph in enumerate(paragraphs):
            if (
                index == 0
                and records
                and should_merge_across_page(records[-1]["text"], paragraph)
            ):
                records[-1]["text"] = _join_continued_paragraph(
                    records[-1]["text"], paragraph
                )
                _append_pdf_page(records[-1], pdf_page)
                continue

            records.append({"text": paragraph, "pdf_pages": [pdf_page]})

    return coalesce_section_heading_records(records)


def coalesce_section_heading_records(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach short section headings like （一）气概念的形成 to their body."""
    merged_records: list[dict[str, Any]] = []
    index = 0

    while index < len(records):
        record = records[index]
        next_record = records[index + 1] if index + 1 < len(records) else None

        if (
            next_record is not None
            and is_short_section_heading(str(record["text"]))
            and not is_section_start(str(next_record["text"]))
        ):
            merged_records.append(
                {
                    "text": _join_record_text([record, next_record]),
                    "pdf_pages": _merge_pdf_pages([record, next_record]),
                }
            )
            index += 2
            continue

        merged_records.append(record)
        index += 1

    return merged_records


def is_short_section_heading(text: str) -> bool:
    """Return True for short marker headings that should stay with their body."""
    compact = re.sub(r"\s+", "", text.strip())
    if len(compact) > SECTION_HEADING_MAX_CHARS:
        return False
    if not is_section_start(compact):
        return False
    return not SENTENCE_PUNCTUATION_PATTERN.search(compact)


def should_merge_across_page(previous_text: str, current_text: str) -> bool:
    """Decide whether a page's first paragraph continues the previous page."""
    previous_text = previous_text.strip()
    current_text = current_text.strip()
    if not previous_text or not current_text:
        return False
    if is_section_start(current_text) or is_structural_heading_start(current_text):
        return False
    if _ends_with_terminal_punctuation(previous_text):
        return False
    if _looks_like_standalone_heading(previous_text):
        return False
    return True


def is_structural_heading_start(text: str) -> bool:
    return bool(STRUCTURAL_HEADING_START_PATTERN.match(text))


def _ends_with_terminal_punctuation(text: str) -> bool:
    text = text.rstrip()
    while text and text[-1] in CLOSING_PUNCTUATION:
        text = text[:-1].rstrip()
    return bool(text) and text[-1] in TERMINAL_PUNCTUATION


def _looks_like_standalone_heading(text: str) -> bool:
    compact = re.sub(r"\s+", "", text.strip())
    if not compact or _has_unmatched_open_punctuation(compact):
        return False
    if len(compact) > 40:
        return False
    if CAPTION_OR_FRONT_MATTER_PATTERN.match(compact):
        return True
    starts_like_heading = is_section_start(compact) or is_structural_heading_start(compact)
    return starts_like_heading and not PHRASE_PUNCTUATION_PATTERN.search(compact)


def _has_unmatched_open_punctuation(text: str) -> bool:
    pairs = [("《", "》"), ("“", "”"), ("（", "）"), ("(", ")")]
    return any(text.count(open_mark) > text.count(close_mark) for open_mark, close_mark in pairs)


def _join_continued_paragraph(previous_text: str, current_text: str) -> str:
    previous_text = previous_text.rstrip()
    current_text = current_text.lstrip()
    if not previous_text or not current_text:
        return previous_text + current_text
    if previous_text[-1].isascii() and current_text[0].isascii():
        return previous_text + " " + current_text
    if previous_text[-1] in "》”" and current_text[0] in "《“":
        return previous_text + " " + current_text
    return previous_text + current_text


def _append_pdf_page(record: dict[str, Any], pdf_page: int) -> None:
    if pdf_page not in record["pdf_pages"]:
        record["pdf_pages"].append(pdf_page)


def chunk_paragraph_records(
    paragraph_records: list[dict[str, Any]],
    chunk_size: int,
    overlap: int,
) -> list[dict[str, Any]]:
    """Chunk paragraph records while preserving their source PDF pages."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0:
        raise ValueError("overlap must be non-negative")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    chunks: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []

    for record in paragraph_records:
        text = str(record["text"])
        if current and is_section_start(text) and not (
            current_starts_with_bracketed_heading(current)
            and is_ordered_list_start(text)
        ):
            chunks.append(_make_chunk_record(current))
            current = []

        if len(text) > chunk_size:
            if current:
                chunks.append(_make_chunk_record(current))
                current = []
            for piece in _split_long_paragraph(text, chunk_size, overlap):
                chunks.append({"text": piece, "pdf_pages": list(record["pdf_pages"])})
            continue

        candidate = _join_record_text([*current, record])
        if current and len(candidate) > chunk_size:
            if is_short_section_heading(str(current[-1]["text"])) and not is_section_start(
                text
            ):
                carried_heading = current.pop()
                if current:
                    chunks.append(_make_chunk_record(current))
                current = [carried_heading]
            else:
                chunks.append(_make_chunk_record(current))
                current = _record_overlap_tail(current, overlap)

                candidate = _join_record_text([*current, record])
                if len(candidate) > chunk_size:
                    current = []

        current.append(record)

    if current:
        chunks.append(_make_chunk_record(current))

    return chunks


def current_starts_with_bracketed_heading(records: list[dict[str, Any]]) -> bool:
    if not records:
        return False
    return is_short_section_heading(str(records[0]["text"])) and is_bracketed_section_start(
        str(records[0]["text"])
    )


def _make_chunk_record(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "text": _join_record_text(records),
        "pdf_pages": _merge_pdf_pages(records),
    }


def _join_record_text(records: Iterable[dict[str, Any]]) -> str:
    return _join_paragraphs(str(record["text"]) for record in records)


def _merge_pdf_pages(records: Iterable[dict[str, Any]]) -> list[int]:
    pages: list[int] = []
    for record in records:
        for page in record["pdf_pages"]:
            if page not in pages:
                pages.append(page)
    return pages


def _record_overlap_tail(
    paragraph_records: list[dict[str, Any]], overlap: int
) -> list[dict[str, Any]]:
    """Keep whole trailing paragraph records as overlap for the next chunk."""
    if overlap == 0:
        return []

    tail: list[dict[str, Any]] = []
    total = 0
    for record in reversed(paragraph_records):
        tail.insert(0, record)
        total += len(str(record["text"]))
        if total >= overlap:
            break
    return tail


def _split_long_paragraph(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Fallback for paragraphs that are longer than chunk_size.

    Long paragraphs are split without character overlap so the next chunk does
    not begin in the middle of a word or phrase.
    """
    chunks: list[str] = []
    start = 0
    while start < len(text):
        proposed_end = min(start + chunk_size, len(text))
        end = _choose_sentence_boundary(text, start, proposed_end)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(text):
            break
        start = end
    return chunks


def _choose_sentence_boundary(
    text: str, start: int, proposed_end: int, min_keep: int = 180
) -> int:
    """Prefer ending a long paragraph chunk at sentence-like punctuation."""
    if proposed_end == len(text) or proposed_end - start <= min_keep:
        return proposed_end

    punctuation = "。！？.!?"
    window = text[start:proposed_end]
    best = max(window.rfind(mark) for mark in punctuation)
    if best >= min_keep:
        return start + best + 1
    return proposed_end


def build_chunks(
    pages: Iterable[dict[str, Any]],
    source_url: str = DEFAULT_SOURCE_URL,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = 80,
    title: str = "TCM Basic Theory",
    skip_first_pages: int = DEFAULT_SKIP_FIRST_PAGES,
) -> list[dict[str, Any]]:
    """Create chunk records with page citation metadata."""
    if skip_first_pages < 0:
        raise ValueError("skip_first_pages must be non-negative")

    chunks: list[dict[str, Any]] = []
    paragraph_records = build_paragraph_records(
        pages, skip_first_pages=skip_first_pages
    )
    chunk_records = chunk_paragraph_records(
        paragraph_records,
        chunk_size=chunk_size,
        overlap=overlap,
    )
    chunk_counts_by_start_page: dict[int, int] = {}

    for chunk_record in chunk_records:
        pdf_pages = list(chunk_record["pdf_pages"])
        if not pdf_pages:
            continue

        start_page = pdf_pages[0]
        end_page = pdf_pages[-1]
        chunk_counts_by_start_page[start_page] = (
            chunk_counts_by_start_page.get(start_page, 0) + 1
        )
        chunk_index = chunk_counts_by_start_page[start_page]

        chunks.append(
            {
                "chunk_id": make_chunk_id(start_page, end_page, chunk_index),
                "text": chunk_record["text"],
                "citation_link": make_citation_url(source_url, start_page),
                "pdf_page": start_page,
                "pdf_page_start": start_page,
                "pdf_page_end": end_page,
                "pdf_pages": pdf_pages,
                "citation_links": [
                    make_citation_url(source_url, pdf_page) for pdf_page in pdf_pages
                ],
                "citation_markdown": make_citation_markdown(
                    title, source_url, pdf_pages
                ),
            }
        )

    return chunks


def make_chunk_id(start_page: int, end_page: int, chunk_index: int) -> str:
    page_part = f"p{start_page}" if start_page == end_page else f"p{start_page}-{end_page}"
    return f"{page_part}_c{chunk_index}"


def make_citation_url(source_url: str, pdf_page: int) -> str:
    """Append a PDF page fragment to a URL."""
    base = source_url.split("#", 1)[0]
    return f"{base}#page={pdf_page}"


def make_citation_markdown(
    title: str, source_url: str, pdf_pages: list[int]
) -> str:
    """Build a Markdown citation, linking page ranges to their first page."""
    start_page = pdf_pages[0]
    end_page = pdf_pages[-1]
    citation_url = make_citation_url(source_url, start_page)
    if start_page == end_page:
        return f"[{title} p.{start_page}]({citation_url})"
    return f"[{title} pp.{start_page}-{end_page}]({citation_url})"


def save_chunks_jsonl(chunks: Iterable[dict[str, Any]], output_path: str | Path) -> None:
    """Save chunks as JSONL, one JSON object per line."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        for chunk in chunks:
            file.write(json.dumps(chunk, ensure_ascii=False) + "\n")


def load_chunks_jsonl(input_path: str | Path) -> list[dict[str, Any]]:
    """Load chunks saved by save_chunks_jsonl."""
    input_path = Path(input_path)
    chunks = []
    with input_path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    return chunks


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract PDF chunks for RAG.")
    parser.add_argument("pdf_path", help="Path to the PDF file.")
    parser.add_argument(
        "-o",
        "--output",
        default=".rag/chunks.jsonl",
        help="Output JSONL path. Default: .rag/chunks.jsonl",
    )
    parser.add_argument(
        "--source-url",
        default=DEFAULT_SOURCE_URL,
        help="Original PDF URL used for citation links.",
    )
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--overlap", type=int, default=80)
    parser.add_argument("--title", default="TCM Basic Theory")
    parser.add_argument(
        "--skip-first-pages",
        type=int,
        default=DEFAULT_SKIP_FIRST_PAGES,
        help=(
            "Skip the first N PDF pages before chunking. "
            f"Default: {DEFAULT_SKIP_FIRST_PAGES}"
        ),
    )
    args = parser.parse_args()

    pages = extract_pages(args.pdf_path)
    chunks = build_chunks(
        pages,
        source_url=args.source_url,
        chunk_size=args.chunk_size,
        overlap=args.overlap,
        title=args.title,
        skip_first_pages=args.skip_first_pages,
    )
    save_chunks_jsonl(chunks, args.output)

    non_empty_pages = sum(1 for page in pages if page.get("text"))
    print(f"Extracted {len(pages)} PDF pages; {non_empty_pages} had text.")
    print(f"Saved {len(chunks)} chunks to {args.output}.")


if __name__ == "__main__":
    main()
