"""Format vector source citations for storage, API telemetry, and UI display."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

DISPLAY_TITLE_MAX_LEN = 48

TRAILING_PUNCTUATION_RE = re.compile(r"[.;:\s]+$")
STORED_ELLIPSIS_RE = re.compile(r"\.{2,}")


def normalize_stored_citation_field(value: str) -> str:
    """Normalize one stored citation field: no trailing punctuation or ellipsis."""
    cleaned = str(value or "").strip()
    if not cleaned:
        return ""

    cleaned = STORED_ELLIPSIS_RE.sub("", cleaned).strip()
    return TRAILING_PUNCTUATION_RE.sub("", cleaned).strip()


def compose_source_citation(
    title: str,
    *,
    volume: Optional[str] = None,
    chapter: Optional[str] = None,
) -> str:
    """Join stored citation parts with the canonical ` - ` separator."""
    parts: List[str] = []
    normalized_title = normalize_stored_citation_field(title)
    if normalized_title:
        parts.append(normalized_title)

    normalized_volume = normalize_stored_citation_field(volume or "")
    if normalized_volume:
        parts.append(normalized_volume)

    normalized_chapter = normalize_stored_citation_field(chapter or "")
    if normalized_chapter:
        parts.append(normalized_chapter)

    return " - ".join(parts)


def format_source_title(title: str, *, max_len: int = DISPLAY_TITLE_MAX_LEN) -> str:
    """Strip trailing punctuation and truncate long composed citation strings for display."""
    cleaned = title.strip()
    if not cleaned:
        return ""

    # Backward compatibility for legacy vector rows that still store trailing ellipsis.
    if not cleaned.endswith("..."):
        cleaned = TRAILING_PUNCTUATION_RE.sub("", cleaned).strip()

    if len(cleaned) <= max_len:
        return cleaned

    if max_len <= 3:
        return "..."

    return cleaned[: max_len - 3].rstrip() + "..."


def format_source_citation(
    title: str,
    *,
    volume: Optional[str] = None,
    chapter: Optional[str] = None,
    max_len: int = DISPLAY_TITLE_MAX_LEN,
) -> str:
    """Compose a citation and truncate the title while keeping volume/chapter visible."""
    normalized_title = normalize_stored_citation_field(title)
    suffix_parts: List[str] = []

    normalized_volume = normalize_stored_citation_field(volume or "")
    if normalized_volume:
        suffix_parts.append(normalized_volume)

    normalized_chapter = normalize_stored_citation_field(chapter or "")
    if normalized_chapter:
        suffix_parts.append(normalized_chapter)

    if not suffix_parts:
        return format_source_title(normalized_title, max_len=max_len)

    suffix = " - " + " - ".join(suffix_parts)
    if not normalized_title:
        return format_source_title(suffix.removeprefix(" - "), max_len=max_len)

    composed = normalized_title + suffix
    if len(composed) <= max_len:
        return composed

    title_budget = max_len - len(suffix)
    if title_budget <= 3:
        return format_source_title(composed, max_len=max_len)

    return format_source_title(normalized_title, max_len=title_budget) + suffix


def citation_from_metadata(metadata: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """Build a structured citation dict from one vector chunk metadata row."""
    title = normalize_stored_citation_field(str(metadata.get("source_title") or ""))
    volume = normalize_stored_citation_field(str(metadata.get("source_volume") or ""))
    chapter = normalize_stored_citation_field(str(metadata.get("source_chapter") or ""))
    return {
        "title": title,
        "volume": volume or None,
        "chapter": chapter or None,
    }


def citation_dedupe_key(citation: Dict[str, Optional[str]]) -> Tuple[str, str, str]:
    """Stable dedupe key for telemetry source lists."""
    return (
        citation.get("title") or "",
        citation.get("volume") or "",
        citation.get("chapter") or "",
    )
