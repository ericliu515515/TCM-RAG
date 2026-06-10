from __future__ import annotations

import re
from urllib.parse import quote, unquote, urlparse


CITATION_SOURCE_QUERY_PARAM = "citation_source"
CITATION_PAGE_QUERY_PARAM = "citation_page"
MARKDOWN_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
PAGE_FRAGMENT_PATTERN = re.compile(r"(?:^|&)page=(\d+)")


def build_app_citation_url(source_id: str, page: int) -> str:
    return (
        f"?{CITATION_SOURCE_QUERY_PARAM}={quote(source_id)}"
        f"&{CITATION_PAGE_QUERY_PARAM}={int(page)}"
    )


def parse_positive_page(value) -> int | None:
    try:
        page = int(value)
    except (TypeError, ValueError):
        return None

    if page <= 0:
        return None

    return page


def parse_citation_page_from_url(url: str) -> int | None:
    fragment = urlparse(url).fragment
    match = PAGE_FRAGMENT_PATTERN.search(fragment)
    if not match:
        return None

    return parse_positive_page(match.group(1))


def source_id_for_citation_url(url: str, sources: list[dict]) -> str | None:
    parsed = urlparse(url)

    if parsed.scheme == "source":
        source_id = unquote(parsed.netloc or parsed.path.lstrip("/")).strip()
        return source_id or None

    base_url = url.split("#", 1)[0]

    for source in sources:
        metadata = source.get("metadata") or {}
        for key in ("viewer_url", "pdf_url", "source_url"):
            candidate = str(metadata.get(key) or "").strip()
            if candidate and candidate.split("#", 1)[0] == base_url:
                return str(source.get("id") or "").strip() or None

    return None


def resolve_citation_target(url: str, sources: list[dict]) -> tuple[str, int] | None:
    source_id = source_id_for_citation_url(url, sources)
    page = parse_citation_page_from_url(url)

    if not source_id or page is None:
        return None

    return source_id, page


def rewrite_markdown_citation_links(markdown_text: str, sources: list[dict]) -> str:
    if not markdown_text:
        return markdown_text

    def replace_link(match: re.Match[str]) -> str:
        label, url = match.groups()
        target = resolve_citation_target(url, sources)
        if target is None:
            return match.group(0)

        source_id, page = target
        return f"[{label}]({build_app_citation_url(source_id, page)})"

    return MARKDOWN_LINK_PATTERN.sub(replace_link, markdown_text)
