from __future__ import annotations

"""Prepare and ingest speaker source texts into Upstash Vector.

The script is organized in three stages:
1. speaker-specific source extraction
2. speaker-specific chunking
3. payload construction and optional Upstash upsert
"""

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Pattern, Sequence, Tuple

from dotenv import load_dotenv


SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
REPO_ROOT = BACKEND_DIR.parent

load_dotenv(REPO_ROOT / ".env")

UPSTASH_VECTOR_REST_URL = os.environ.get("UPSTASH_VECTOR_REST_URL")
UPSTASH_VECTOR_REST_TOKEN = os.environ.get("UPSTASH_VECTOR_REST_TOKEN")
UPSTASH_VECTOR_MAX_BATCH_SIZE = 1000


AGENT_SOURCE_CONFIG: Dict[str, Dict[str, str]] = {
    "agt_001": {
        "speaker_name": "Socrates",
        "source_title": "Apology",
        "author": "Plato",
        "translator": "Benjamin Jowett",
        "source_type": "dialogue",
        "voice_type": "primary_adjacent",
        "source_slug": "apology",
        "section": "apology_body",
    },
    "agt_002": {
        "speaker_name": "Steve Jobs",
        "source_title": "Stanford Commencement Address",
        "author": "Steve Jobs",
        "translator": "",
        "source_type": "speech",
        "voice_type": "primary",
        "source_slug": "stanford_commencement",
        "section": "speech_body",
    },
    "agt_003": {
        "speaker_name": "Sun Tzu",
        "source_title": "The Art of War",
        "author": "Sun Tzu",
        "translator": "Lionel Giles",
        "source_type": "treatise",
        "voice_type": "primary",
        "source_slug": "art_of_war",
        "section": "handbook_body",
    },
    "agt_004": {
        "speaker_name": "Napoleon Bonaparte",
        "source_title": "Memoirs of the life...",
        "author": "Emmanuel-Auguste-Dieudonne Las Cases",
        "translator": "",
        "source_type": "memoir",
        "voice_type": "primary_adjacent",
        "source_slug": "memoirs_of_the_life",
        "section": "anchor_windows",
    },
    "agt_005": {
        "speaker_name": "Marcus Aurelius",
        "source_title": "Meditations",
        "author": "Marcus Aurelius",
        "translator": "",
        "source_type": "meditations",
        "voice_type": "primary",
        "source_slug": "meditations_selected",
        "section": "selected_books",
    },
    "agt_006": {
        "speaker_name": "Cleopatra",
        "source_title": "Life of Antony - Cleopatra arc",
        "author": "Plutarch",
        "translator": "John Dryden",
        "source_type": "biography",
        "voice_type": "primary_adjacent",
        "source_slug": "life_of_antony_cleopatra_arc",
        "section": "cleopatra_arc",
    },
    "agt_007": {
        "speaker_name": "Leonardo da Vinci",
        "source_title": "Thoughts on Art and Life",
        "author": "Leonardo da Vinci",
        "translator": "Maurice Baring",
        "source_type": "notebook_fragments",
        "voice_type": "primary",
        "source_slug": "thoughts_on_art_and_life",
        "section": "collected_thoughts",
    },
    "agt_008": {
        "speaker_name": "Ada Lovelace",
        "source_title": "Notes on the Analytical Engine",
        "author": "Ada Lovelace",
        "translator": "",
        "source_type": "scientific_notes",
        "voice_type": "primary",
        "source_slug": "notes_on_the_analytical_engine",
        "section": "selected_notes",
    },
    "agt_009": {
        "speaker_name": "Marie Curie",
        "source_title": "Selected Marie Curie narratives",
        "author": "Marie Curie",
        "translator": "Charlotte Kellogg; Vernon L. Kellogg",
        "source_type": "memoir",
        "voice_type": "primary",
        "source_slug": "selected_marie_curie_narratives",
        "section": "selected_chapters",
    },
    "agt_011": {
        "speaker_name": "Leon Trotsky",
        "source_title": "My Life",
        "author": "Leon Trotsky",
        "translator": "",
        "source_type": "memoir",
        "voice_type": "primary",
        "source_slug": "my_life_selected",
        "section": "selected_chapters",
    },
    "agt_012": {
        "speaker_name": "Friedrich Nietzsche",
        "source_title": "The Twilight of the Idols",
        "author": "Friedrich Nietzsche",
        "translator": "Anthony M. Ludovici",
        "source_type": "aphorisms",
        "voice_type": "primary",
        "source_slug": "twilight_of_the_idols_selected",
        "section": "selected_sections",
    },
    "agt_013": {
        "speaker_name": "Nikola Tesla",
        "source_title": "My Inventions",
        "author": "Nikola Tesla",
        "translator": "",
        "source_type": "autobiography",
        "voice_type": "primary",
        "source_slug": "my_inventions",
        "section": "autobiography_body",
    },
    "agt_014": {
        "speaker_name": "Marie Antoinette",
        "source_title": "Marie Antoinette hybrid corpus",
        "author": "Marie Antoinette; Mme. Campan; Count Mercy-Argenteau; Revolutionary Tribunal",
        "translator": "",
        "source_type": "hybrid_corpus",
        "voice_type": "mixed",
        "source_slug": "marie_antoinette_hybrid_corpus",
        "section": "selected_documents",
    }
}

SourceDocument = Dict[str, str]


@dataclass(frozen=True)
class ChunkingPolicy:
    """Declarative chunking controls for one speaker corpus."""

    target_chunk_size: int
    overlap_percent: int
    min_chunk_chars: int
    max_merge_ratio: float
    boundary_patterns: Tuple[str, ...]


@dataclass(frozen=True)
class AgentIngestPlan:
    speaker_name: str
    extraction_summary: str
    chunking_summary: str
    document_extractor: Callable[[str], List[SourceDocument]]
    chunking_policy: ChunkingPolicy


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for ingestion, inspection, and dry-run modes."""
    parser = argparse.ArgumentParser(description="Ingest speaker knowledge into Upstash Vector")
    parser.add_argument("--agent-id", default="agt_001", help="Agent identifier, e.g. agt_001")
    parser.add_argument("--list-agents", action="store_true", help="List supported speaker ingestion plans")
    parser.add_argument("--describe-agent", help="Print the ingestion plan for one agent id and exit")
    parser.add_argument(
        "--source-file",
        default=None,
        help="Path to the source text file. Defaults to data/<agent-id>.txt",
    )
    parser.add_argument("--chunk-size", type=int, default=None, help="Optional override for target chunk size in characters")
    parser.add_argument(
        "--overlap-percent",
        type=int,
        default=None,
        help="Optional override for overlap as a percentage of emitted chunk length",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=None,
        help="Legacy fixed overlap override in characters. Converted to an equivalent overlap percentage.",
    )
    parser.add_argument("--namespace", default="", help="Optional Upstash Vector namespace")
    parser.add_argument("--dry-run", action="store_true", help="Print chunk preview without upserting")
    return parser.parse_args()


def clean_whitespace(text: str) -> str:
    """Normalize line endings and collapse excess whitespace between sections."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def slugify(value: str) -> str:
    """Convert a human-readable source title into a stable metadata slug."""
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower())
    return slug.strip("_") or "source"


def build_source_document(agent_id: str, text: str, **overrides: str) -> Dict[str, str]:
    """Merge base agent source metadata with extracted source text and overrides."""
    document = dict(AGENT_SOURCE_CONFIG[agent_id])
    document.update(overrides)
    document["text"] = clean_whitespace(text)
    return document


def resolve_source_path(agent_id: str, source_file: str | None) -> Path:
    """Resolve the on-disk source file for an agent, honoring explicit overrides."""
    if source_file:
        return Path(source_file)

    return REPO_ROOT / "data" / f"{agent_id}.txt"


def extract_heading_section(text: str, start_heading: str, end_heading: str) -> str:
    """Extract a heading-delimited slice from a structured source text."""
    start_marker = f"\n{start_heading}\n"
    end_marker = f"\n{end_heading}\n"

    start_index = text.find(start_marker)
    if start_index == -1:
        raise ValueError(f"Could not locate section start marker: {start_heading}")

    section_text = text[start_index + 1:]
    end_index = section_text.find(end_marker)
    if end_index == -1:
        raise ValueError(f"Could not locate section end marker after: {start_heading}")

    section_text = clean_whitespace(section_text[:end_index])
    if not section_text:
        raise ValueError(f"Extracted section is empty: {start_heading}")

    return section_text


def extract_project_gutenberg_work_body(
    text: str,
    *,
    ebook_title: str,
    work_heading: str,
) -> str:
    """Extract a single work body from a Project Gutenberg omnibus source file."""
    start_marker = f"*** START OF THE PROJECT GUTENBERG EBOOK {ebook_title.upper()} ***"
    end_marker = f"*** END OF THE PROJECT GUTENBERG EBOOK {ebook_title.upper()} ***"
    heading_marker = f"\n{work_heading}\n"

    start_index = text.find(start_marker)
    if start_index == -1:
        raise ValueError(f"Could not locate Gutenberg start marker for {ebook_title}")

    body = text[start_index + len(start_marker):]
    heading_index = body.find(heading_marker)
    if heading_index == -1:
        raise ValueError(f"Could not locate work heading for {work_heading}")

    body = body[heading_index + len(heading_marker):]
    end_index = body.find(end_marker)
    if end_index != -1:
        body = body[:end_index]

    body = clean_whitespace(body)
    if not body:
        raise ValueError(f"Extracted Gutenberg body is empty: {ebook_title}")

    return body


def extract_project_gutenberg_ebook_body(text: str, *, ebook_title: str) -> str:
    """Extract one Project Gutenberg ebook body without depending on an internal heading."""
    start_marker = f"*** START OF THE PROJECT GUTENBERG EBOOK {ebook_title.upper()} ***"
    end_marker = f"*** END OF THE PROJECT GUTENBERG EBOOK {ebook_title.upper()} ***"

    start_index = text.find(start_marker)
    if start_index == -1:
        raise ValueError(f"Could not locate Gutenberg start marker for {ebook_title}")

    body_start = start_index + len(start_marker)
    end_index = text.find(end_marker, body_start)
    if end_index == -1:
        raise ValueError(f"Could not locate Gutenberg end marker for {ebook_title}")

    body = clean_whitespace(text[body_start:end_index])
    if not body:
        raise ValueError(f"Extracted Gutenberg ebook body is empty: {ebook_title}")

    return body


def extract_between_markers(text: str, *, start_marker: str, end_marker: str) -> str:
    """Extract a contiguous slice from an unstructured source text using exact markers."""
    start_index = text.find(start_marker)
    if start_index == -1:
        raise ValueError(f"Could not locate slice start marker: {start_marker}")

    end_index = text.find(end_marker, start_index + len(start_marker))
    if end_index == -1:
        raise ValueError(f"Could not locate slice end marker: {end_marker}")

    body = clean_whitespace(text[start_index:end_index])
    if not body:
        raise ValueError("Extracted marker-bounded body is empty after cleaning")

    return body


def extract_from_marker(text: str, *, start_marker: str) -> str:
    """Extract a slice from an exact marker to the end of the available text."""
    start_index = text.find(start_marker)
    if start_index == -1:
        raise ValueError(f"Could not locate slice start marker: {start_marker}")

    body = clean_whitespace(text[start_index:])
    if not body:
        raise ValueError("Extracted marker-to-end body is empty after cleaning")

    return body


def extract_apology_body(text: str) -> str:
    """Extract the main Apology dialogue body from the Socrates source file."""
    start_marker = "\nAPOLOGY\n"
    end_marker = "*** END OF THE PROJECT GUTENBERG EBOOK APOLOGY ***"

    start_index = text.find(start_marker)
    if start_index == -1:
        raise ValueError("Could not locate APOLOGY body start marker in source file")

    body = text[start_index + len(start_marker):]
    end_index = body.find(end_marker)
    if end_index != -1:
        body = body[:end_index]

    body = clean_whitespace(body)
    if not body:
        raise ValueError("Extracted APOLOGY body is empty after cleaning")

    return body


def extract_stanford_speech_body(text: str) -> str:
    """Drop the title line and return the main Stanford speech body."""
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    if not lines:
        raise ValueError("Stanford speech source is empty")

    body = "\n".join(lines[1:])
    body = clean_whitespace(body)
    if not body:
        raise ValueError("Extracted Stanford speech body is empty after removing intro line")

    return body


def extract_art_of_war_body(text: str) -> str:
    """Extract the handbook body of The Art of War without Gutenberg framing."""
    start_marker = "\nChapter I. LAYING PLANS\n"
    end_marker = "*** END OF THE PROJECT GUTENBERG EBOOK THE ART OF WAR ***"

    start_index = text.find(start_marker)
    if start_index == -1:
        raise ValueError("Could not locate The Art of War body start marker in source file")

    body = text[start_index + 1:]
    end_index = body.find(end_marker)
    if end_index != -1:
        body = body[:end_index]

    body = clean_whitespace(body)
    if not body:
        raise ValueError("Extracted The Art of War body is empty after cleaning")

    return body


def extract_thoughts_on_art_and_life_body(text: str) -> str:
    """Keep the main Leonardo notebook text and trim bibliography appendices."""
    start_marker = "\nTHOUGHTS ON LIFE\n"
    end_markers = [
        "\nBIBLIOGRAPHICAL NOTE\n",
        "\nTABLE OF REFERENCES\n",
        "*** END OF THE PROJECT GUTENBERG EBOOK THOUGHTS ON ART AND LIFE ***",
    ]

    start_index = text.find(start_marker)
    if start_index == -1:
        raise ValueError("Could not locate Thoughts on Art and Life body start marker in source file")

    body = text[start_index + 1:]
    end_indexes = [body.find(marker) for marker in end_markers if body.find(marker) != -1]
    if end_indexes:
        body = body[:min(end_indexes)]

    body = clean_whitespace(body)
    if not body:
        raise ValueError("Extracted Thoughts on Art and Life body is empty after cleaning")

    return body


def extract_twilight_of_the_idols_selected_body(text: str) -> str:
    """Extract the configured Nietzsche sections that seed the current corpus."""
    section_markers = [
        ("MAXIMS AND MISSILES", "THE PROBLEM OF SOCRATES"),
        ("“REASON” IN PHILOSOPHY", "HOW THE “TRUE WORLD” ULTIMATELY BECAME A FABLE"),
        ("THE FOUR GREAT ERRORS", "THE “IMPROVERS” OF MANKIND"),
        ("SKIRMISHES IN A WAR WITH THE AGE", "THE HAMMER SPEAKETH"),
    ]

    sections: List[str] = []
    for start_heading, end_heading in section_markers:
        sections.append(extract_heading_section(text, start_heading, end_heading))

    body = clean_whitespace("\n\n".join(sections))
    if not body:
        raise ValueError("Extracted selected Nietzsche sections are empty after cleaning")

    return body


def extract_my_life_selected_body(text: str) -> str:
    """Remove site noise and keep the selected Trotsky memoir chapter body."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    kept_lines: List[str] = []

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped:
            kept_lines.append("")
            continue

        if stripped in {"Leon Trotsky", "My Life", "return"}:
            continue
        if stripped.startswith("Last Chapter"):
            continue
        if stripped.startswith("Last updated on:"):
            continue

        kept_lines.append(stripped)

    body = clean_whitespace("\n".join(kept_lines))
    if not body.startswith("CHAPTER "):
        chapter_index = body.find("CHAPTER ")
        if chapter_index == -1:
            raise ValueError("Could not locate selected chapter start in My Life source file")
        body = body[chapter_index:]

    if not body:
        raise ValueError("Extracted My Life body is empty after cleaning")

    return body


def extract_cleopatra_life_of_antony_body(text: str) -> str:
    """Keep the contiguous Cleopatra narrative from first seduction setup through her death."""
    return extract_between_markers(
        text,
        start_marker=(
            "Such being his temper, the last and crowning mischief that could befall him came in the love of Cleopatra"
        ),
        end_marker=(
            "Antony left by his three wives seven children,"
        ),
    )


def extract_pierre_curie_body(text: str) -> str:
    """Extract the Pierre Curie work body from the agt_009 omnibus source file."""
    return extract_project_gutenberg_work_body(
        text,
        ebook_title="Pierre Curie",
        work_heading="PIERRE CURIE",
    )


def extract_curie_autobiographical_notes_body(text: str) -> str:
    """Extract the Marie Curie autobiographical notes section from the Pierre Curie volume."""
    pierre_curie_body = extract_pierre_curie_body(text)
    return extract_from_marker(
        pierre_curie_body,
        start_marker="AUTOBIOGRAPHICAL NOTES\nMARIE CURIE",
    )


NAPOLEON_MEMOIR_VOLUMES: Tuple[str, ...] = (
    "Memoirs of the life, exile, and conversations of the Emperor Napoleon. (Vol. I)",
    "Memoirs of the life, exile, and conversations of the Emperor Napoleon. (Vol. II)",
    "Memoirs of the life, exile, and conversations of the Emperor Napoleon. (Vol. III)",
    "Memoirs of the life, exile, and conversations of the Emperor Napoleon. (Vol. IV)",
)


NAPOLEON_ANCHOR_PATTERNS: Tuple[Tuple[str, Pattern[str]], ...] = (
    ("austerlitz", re.compile(r"\bAusterlitz\b", re.IGNORECASE)),
    ("waterloo", re.compile(r"\bWaterloo\b", re.IGNORECASE)),
    (
        "campaign_of_italy",
        re.compile(r"\bCampaign of Italy\b|\bCisalpine\b", re.IGNORECASE),
    ),
    (
        "russian_campaign",
        re.compile(r"\bMoscow\b|\bBorodino\b|\bRussian campaign\b", re.IGNORECASE),
    ),
    ("marengo", re.compile(r"\bMarengo\b", re.IGNORECASE)),
    (
        "civil_code",
        re.compile(r"\bMy Code\b|\bCivil Code\b|\bNapoleonic Code\b", re.IGNORECASE),
    ),
    (
        "institutions",
        re.compile(r"\bMy institutions\b|\bUniversity\b|\bLegion of Honour\b", re.IGNORECASE),
    ),
    (
        "united_states_of_europe",
        re.compile(r"\bUnited States of Europe\b|\bEuropean association\b", re.IGNORECASE),
    ),
    (
        "unification_of_europe",
        re.compile(r"\bUnification of Europe\b|\bUniversal law\b", re.IGNORECASE),
    ),
)

NAPOLEON_INDEX_LINE_PATTERN = re.compile(
    r"^[A-Za-z][A-Za-z'’.,-]+(?:\s+(?:[A-Za-z][A-Za-z'’.,-]+|of|the|and|de|du|la|le|des)){0,12}\s+\d{1,4}$",
    re.IGNORECASE,
)

NAPOLEON_INDEX_HEADING_PATTERN = re.compile(
    r"\b(table of contents|contents|list of illustrations|illustrations|index)\b",
    re.IGNORECASE,
)

LOVELACE_NOTE_HEADING_PATTERN = re.compile(r"^NOTE [A-G]", re.MULTILINE)
LOVELACE_PAGE_MARKER_PATTERN = re.compile(r"\[Pg \d+\]")
LOVELACE_FORMULA_PARAGRAPH_PATTERN = re.compile(r"^[A-Za-z0-9_{}^\\/+=().,;:& \-]+$")
LOVELACE_COMPLEX_TABLE_PATTERN = re.compile(
    r"\b(array of equations|figure of a|Variables for Data|Variables for Results|Number of operation|Operation-cards|Diagram for the computation)\b",
    re.IGNORECASE,
)


def is_napoleon_index_paragraph(paragraph: str) -> bool:
    """Detect table-of-contents or illustration-index style paragraphs that should not enter narrative windows."""
    lines = [line.strip() for line in paragraph.split("\n") if line.strip()]
    if not lines:
        return True

    joined = " ".join(lines)
    if NAPOLEON_INDEX_HEADING_PATTERN.search(joined):
        return True

    index_like_lines = sum(1 for line in lines if NAPOLEON_INDEX_LINE_PATTERN.fullmatch(line))
    if index_like_lines and index_like_lines / len(lines) >= 0.5:
        return True

    if len(lines) == 1 and NAPOLEON_INDEX_LINE_PATTERN.fullmatch(lines[0]):
        return True

    return False


def extract_napoleon_core(text: str) -> List[str]:
    """Split a Napoleon volume into narrative paragraphs, removing index-style noise blocks first."""
    return [paragraph for paragraph in split_into_paragraphs(text) if not is_napoleon_index_paragraph(paragraph)]


def normalize_lovelace_formula(text: str) -> str:
    """Apply a minimal deterministic cleanup so formula-heavy lines render as LaTeX."""
    formula = clean_whitespace(text)
    formula = formula.replace("Delta", r"\Delta")
    formula = formula.replace("epsilon", r"\epsilon")
    formula = re.sub(r"(?<!\\)\bpi\b", r"\\pi", formula)
    formula = formula.replace("...", r"\ldots")
    formula = formula.replace("&c.", r"\text{etc.}")
    formula = re.sub(r"(?<!\\)\bcos\b", r"\\cos", formula)
    formula = re.sub(r"(?<!\\)\bsin\b", r"\\sin", formula)
    formula = re.sub(r"(?<!\\)\blog\b", r"\\log", formula)
    formula = re.sub(r"\s*=\s*", " = ", formula)
    return formula


def is_lovelace_formula_paragraph(paragraph: str) -> bool:
    """Identify short standalone mathematical paragraphs that should be emitted as block LaTeX."""
    compact = clean_whitespace(paragraph)
    if not compact or len(compact) > 220:
        return False
    if any(token in compact for token in ("The ", "We ", "It ", "This ", "Those ", "These ")):
        return False
    if LOVELACE_COMPLEX_TABLE_PATTERN.search(compact):
        return False
    math_tokens = sum(compact.count(token) for token in ("=", "^{", "_", "(", ")", "/", "Delta", "B_", "x", "u_"))
    return math_tokens >= 2 and bool(LOVELACE_FORMULA_PARAGRAPH_PATTERN.fullmatch(compact))


def translate_lovelace_complex_block(paragraph: str) -> str:
    """Convert table and operation-sequence references into structured prose rather than raw columns."""
    compact = clean_whitespace(paragraph)
    if "Bernoulli" not in compact and not LOVELACE_COMPLEX_TABLE_PATTERN.search(compact):
        return compact

    return clean_whitespace(
        "### Engine Workflow Summary\n"
        "- The engine treats previously computed Bernoulli numbers as reusable inputs for the next result.\n"
        "- It advances through a recurring card cycle that builds the needed coefficients from n, combines them with prior Bernoulli values, and stores the new Bernoulli number on the next result column.\n"
        "- The diagram and table are intentionally replaced with prose here, because the important retrieval signal is the ordered workflow of variables, operations, and result columns rather than raw page-layout data."
    )


def normalize_lovelace_note_text(note_text: str) -> str:
    """Keep explanatory prose, render formulas as LaTeX, and replace raw diagrams/tables with markdown summaries."""
    note_text = LOVELACE_PAGE_MARKER_PATTERN.sub("", note_text)
    paragraphs = split_into_paragraphs(note_text)
    normalized_paragraphs: List[str] = []

    for paragraph in paragraphs:
        compact = clean_whitespace(paragraph)
        if not compact:
            continue
        if LOVELACE_COMPLEX_TABLE_PATTERN.search(compact):
            normalized_paragraphs.append(translate_lovelace_complex_block(compact))
            continue
        if compact.startswith("Here follows a repetition of Operations"):
            normalized_paragraphs.append(translate_lovelace_complex_block(compact))
            continue
        if is_lovelace_formula_paragraph(compact):
            normalized_paragraphs.append(f"$$\n{normalize_lovelace_formula(compact)}\n$$")
            continue
        normalized_paragraphs.append(compact)

    return clean_whitespace("\n\n".join(normalized_paragraphs))


def extract_lovelace_notes(text: str) -> List[SourceDocument]:
    """Extract Note A and a prose-forward Note G from Lovelace's Analytical Engine notes."""
    note_a = extract_between_markers(
        text,
        start_marker="NOTE A.—Page 9.",
        end_marker="NOTE B.—Page 11.",
    )
    note_g = extract_between_markers(
        text,
        start_marker="NOTE G.—Page 24.",
        end_marker="The diagram[30] represents the columns of the engine when just",
    )

    note_g_diagram_present = "Diagram for the computation by the Engine of the Numbers of Bernoulli." in text
    normalized_note_g = normalize_lovelace_note_text(note_g)
    if note_g_diagram_present:
        normalized_note_g = clean_whitespace(
            normalized_note_g
            + "\n\n"
            + translate_lovelace_complex_block("Diagram for the computation by the Engine of the Numbers of Bernoulli.")
        )

    return [
        build_source_document(
            "agt_008",
            normalize_lovelace_note_text(note_a),
            source_title="Note A - Analytical Engine Scope",
            source_slug="note_a_analytical_engine_scope",
            section="note_a",
            source_type="scientific_note",
        ),
        build_source_document(
            "agt_008",
            normalized_note_g,
            source_title="Note G - Engine Limits and Bernoulli Method",
            source_slug="note_g_engine_limits_bernoulli_method",
            section="note_g",
            source_type="scientific_note",
        ),
    ]


def split_into_paragraphs(text: str) -> List[str]:
    """Split normalized prose into paragraph units for deterministic context windows."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return [clean_whitespace(segment) for segment in re.split(r"\n\s*\n+", normalized) if clean_whitespace(segment)]


def extract_anchor_context_documents(
    *,
    agent_id: str,
    text: str,
    before_paragraphs: int,
    after_paragraphs: int,
    volume_label: str,
) -> List[SourceDocument]:
    """Extract paragraph windows around exact anchor hits using deterministic regex matching."""
    paragraphs = extract_napoleon_core(text)
    matched_windows: List[Tuple[int, int, str]] = []
    anchor_counts: Dict[str, int] = {}

    for paragraph_index, paragraph in enumerate(paragraphs):
        for anchor_slug, pattern in NAPOLEON_ANCHOR_PATTERNS:
            if not pattern.search(paragraph):
                continue

            start_index = max(0, paragraph_index - before_paragraphs)
            end_index = min(len(paragraphs), paragraph_index + after_paragraphs + 1)
            if matched_windows and start_index < matched_windows[-1][1]:
                previous_start, previous_end, previous_anchor = matched_windows[-1]
                matched_windows[-1] = (previous_start, max(previous_end, end_index), previous_anchor)
                break

            matched_windows.append((start_index, end_index, anchor_slug))
            break

    documents: List[SourceDocument] = []
    for start_index, end_index, anchor_slug in matched_windows:
        anchor_counts[anchor_slug] = anchor_counts.get(anchor_slug, 0) + 1
        documents.append(
            build_source_document(
                agent_id,
                "\n\n".join(paragraphs[start_index:end_index]),
                source_title="Memoirs of the life...",
                source_slug=f"memoirs_of_the_life_{volume_label}_{anchor_slug}_{anchor_counts[anchor_slug]:04d}",
                section=f"{volume_label}_{anchor_slug}_context_window",
                source_type="memoir",
                voice_type="primary_adjacent",
            )
        )

    return documents


def extract_napoleon_source_documents(text: str) -> List[SourceDocument]:
    """Extract deterministic paragraph windows around requested Napoleon anchors across all four volumes."""
    documents: List[SourceDocument] = []

    for volume_number, ebook_title in enumerate(NAPOLEON_MEMOIR_VOLUMES, start=1):
        volume_body = extract_project_gutenberg_ebook_body(text, ebook_title=ebook_title)
        documents.extend(
            extract_anchor_context_documents(
                agent_id="agt_004",
                text=volume_body,
                before_paragraphs=3,
                after_paragraphs=5,
                volume_label=f"vol_{volume_number}",
            )
        )

    if not documents:
        raise ValueError("Could not extract any Napoleon anchor windows from agt_004.txt")

    return documents


def extract_my_inventions_body(text: str) -> str:
    """Extract Tesla's autobiography body between the configured start and footer markers."""
    start_marker = "\nI. My Early Life.\n"
    end_marker = "\n\n\n\nThis work is in the public domain in the United States"

    start_index = text.find(start_marker)
    if start_index == -1:
        raise ValueError("Could not locate My Inventions body start marker in source file")

    body = text[start_index + 1:]
    end_index = body.find(end_marker)
    if end_index != -1:
        body = body[:end_index]

    body = clean_whitespace(body)
    if not body:
        raise ValueError("Extracted My Inventions body is empty after cleaning")

    return body


MARIE_ANTOINETTE_DOCUMENT_MARKERS: Tuple[Tuple[str, str, str], ...] = (
    (
        "PRIMARY SOURCE DOCUMENT 1: MARIE ANTOINETTE TO HER MOTHER (MARIA THERESA)",
        "HISTORICAL RECORD 2: THE AMBASSADOR'S REPORT ON EXTRAVAGANCE (COUNT MERCY-ARGENTEAU, 1776)",
        "letter_to_maria_theresa_1773",
    ),
    (
        "HISTORICAL RECORD 2: THE AMBASSADOR'S REPORT ON EXTRAVAGANCE (COUNT MERCY-ARGENTEAU, 1776)",
        "HISTORICAL RECORD 3: MEMOIRS OF THE COURT OF MARIE ANTOINETTE (BY MADAME CAMPAN)",
        "ambassador_report_extravagance_1776",
    ),
    (
        "HISTORICAL RECORD 3: MEMOIRS OF THE COURT OF MARIE ANTOINETTE (BY MADAME CAMPAN)",
        "HISTORICAL RECORD 4: THE OFFICIAL INDICTMENT AND TRIAL ACCUSATIONS (OCTOBER 1793)",
        "campan_summary_record",
    ),
    (
        "HISTORICAL RECORD 4: THE OFFICIAL INDICTMENT AND TRIAL ACCUSATIONS (OCTOBER 1793)",
        "PRIMARY SOURCE DOCUMENT 5: THE LAST LETTER OF MARIE ANTOINETTE TO MADAME ÉLISABETH",
        "trial_indictment_1793",
    ),
    (
        "PRIMARY SOURCE DOCUMENT 5: THE LAST LETTER OF MARIE ANTOINETTE TO MADAME ÉLISABETH",
        "The Project Gutenberg eBook of Memoirs of the Court of Marie Antoinette, Queen of France, Complete",
        "last_letter_to_madame_elisabeth_1793",
    ),
)


def extract_marie_antoinette_campan_body(text: str) -> str:
    """Extract the Project Gutenberg Campan memoir body while dropping illustrations and license boilerplate."""
    campan_ebook_body = extract_project_gutenberg_ebook_body(
        text,
        ebook_title="Memoirs of the Court of Marie Antoinette, Queen of France, Complete",
    )
    return extract_from_marker(campan_ebook_body, start_marker="PREFACE BY THE AUTHOR.")


def extract_marie_antoinette_source_documents(text: str) -> List[SourceDocument]:
    """Build the Marie Antoinette source set from curated documents plus a cleaned Campan memoir body."""
    extracted_documents = {
        section: extract_between_markers(text, start_marker=start_marker, end_marker=end_marker)
        for start_marker, end_marker, section in MARIE_ANTOINETTE_DOCUMENT_MARKERS
    }
    campan_body = extract_marie_antoinette_campan_body(text)

    return [
        build_source_document(
            "agt_014",
            extracted_documents["letter_to_maria_theresa_1773"],
            source_title="Letter to Maria Theresa (1773)",
            source_slug="letter_to_maria_theresa_1773",
            section="letter_to_maria_theresa_1773",
            source_type="letter",
            voice_type="primary",
        ),
        build_source_document(
            "agt_014",
            extracted_documents["ambassador_report_extravagance_1776"],
            source_title="Mercy-Argenteau Report (1776)",
            source_slug="mercy_argenteau_report_1776",
            section="ambassador_report_extravagance_1776",
            source_type="historical_record",
            voice_type="primary_adjacent",
        ),
        build_source_document(
            "agt_014",
            extracted_documents["campan_summary_record"],
            source_title="Campan Court Record",
            source_slug="campan_court_record",
            section="campan_summary_record",
            source_type="historical_record",
            voice_type="primary_adjacent",
        ),
        build_source_document(
            "agt_014",
            extracted_documents["trial_indictment_1793"],
            source_title="Trial Indictment (1793)",
            source_slug="trial_indictment_1793",
            section="trial_indictment_1793",
            source_type="indictment",
            voice_type="primary_adjacent",
        ),
        build_source_document(
            "agt_014",
            extracted_documents["last_letter_to_madame_elisabeth_1793"],
            source_title="Last Letter to Madame Elisabeth",
            source_slug="last_letter_to_madame_elisabeth_1793",
            section="last_letter_to_madame_elisabeth_1793",
            source_type="letter",
            voice_type="primary",
        ),
        build_source_document(
            "agt_014",
            campan_body,
            source_title="Memoirs of the Court of Marie Antoinette",
            source_slug="memoirs_of_the_court_of_marie_antoinette",
            section="campan_memoirs_body",
            source_type="memoir",
            voice_type="primary_adjacent",
        ),
    ]


def extract_jobs_source_documents(text: str) -> List[Dict[str, str]]:
    """Split the Steve Jobs corpus into speech, interview, keynote, or letter documents."""
    normalized_text = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    separator_pattern = re.compile(r"(?:^|\n)-{5,}\n(?P<title>[^\n]+)\n-{5,}\n")
    matches = list(separator_pattern.finditer(normalized_text))

    documents: List[Dict[str, str]] = []

    if not matches:
        return [
            build_source_document(
                "agt_002",
                extract_stanford_speech_body(normalized_text),
                source_title="Stanford Commencement Address",
                source_slug="stanford_commencement",
                section="speech_body",
                source_type="speech",
            )
        ]

    leading_segment = normalized_text[:matches[0].start()].strip()
    if leading_segment:
        documents.append(
            build_source_document(
                "agt_002",
                extract_stanford_speech_body(leading_segment),
                source_title="Stanford Commencement Address",
                source_slug="stanford_commencement",
                section="speech_body",
                source_type="speech",
            )
        )

    for index, match in enumerate(matches):
        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized_text)
        title = match.group("title").strip()
        body = clean_whitespace(normalized_text[body_start:body_end])
        if not body:
            continue

        lower_title = title.lower()
        source_type = "speech"
        if "interview" in lower_title:
            source_type = "interview"
        elif "letter" in lower_title:
            source_type = "open_letter"
        elif "keynote" in lower_title:
            source_type = "keynote"

        documents.append(
            build_source_document(
                "agt_002",
                body,
                source_title=title,
                source_slug=slugify(title),
                section=slugify(title),
                source_type=source_type,
            )
        )

    if not documents:
        raise ValueError("Could not extract any Steve Jobs source documents from agt_002.txt")

    return documents


def extract_socrates_source_documents(text: str) -> List[SourceDocument]:
    """Build the Socrates source set from the Apology and Crito texts."""
    return [
        build_source_document(
            "agt_001",
            extract_apology_body(text),
            source_title="Apology",
            source_slug="apology",
            section="apology_body",
            source_type="dialogue",
            voice_type="primary_adjacent",
        ),
        build_source_document(
            "agt_001",
            extract_project_gutenberg_work_body(text, ebook_title="Crito", work_heading="CRITO"),
            source_title="Crito",
            source_slug="crito",
            section="crito_body",
            source_type="dialogue",
            voice_type="primary_adjacent",
        ),
    ]


def extract_meditations_source_documents(text: str) -> List[SourceDocument]:
    """Build the Marcus Aurelius source set from the selected Meditations books."""
    return [
        build_source_document(
            "agt_005",
            extract_heading_section(text, "THE SECOND BOOK", "THE THIRD BOOK"),
            source_title="Meditations - Second Book",
            source_slug="meditations_second_book",
            section="second_book",
            source_type="meditations",
        ),
        build_source_document(
            "agt_005",
            extract_heading_section(text, "THE FOURTH BOOK", "THE FIFTH BOOK"),
            source_title="Meditations - Fourth Book",
            source_slug="meditations_fourth_book",
            section="fourth_book",
            source_type="meditations",
        ),
    ]


def extract_sun_tzu_source_documents(text: str) -> List[SourceDocument]:
    """Build the Sun Tzu source set from the extracted Art of War body."""
    return [build_source_document("agt_003", extract_art_of_war_body(text))]


def extract_napoleon_source_documents_wrapper(text: str) -> List[SourceDocument]:
    """Build the Napoleon source set from anchor-bounded paragraph windows."""
    return extract_napoleon_source_documents(text)


def extract_lovelace_source_documents(text: str) -> List[SourceDocument]:
    """Build the Ada Lovelace source set from Note A and Note G only."""
    return extract_lovelace_notes(text)


def extract_cleopatra_source_documents(text: str) -> List[SourceDocument]:
    """Build the Cleopatra source set from the relevant Life of Antony narrative slice."""
    return [build_source_document("agt_006", extract_cleopatra_life_of_antony_body(text))]


def extract_curie_source_documents(text: str) -> List[SourceDocument]:
    """Build the Marie Curie source set from the requested narrative chapters only."""
    pierre_curie_body = extract_pierre_curie_body(text)
    autobiographical_notes_body = extract_curie_autobiographical_notes_body(text)

    return [
        build_source_document(
            "agt_009",
            extract_heading_section(pierre_curie_body, "CHAPTER V", "CHAPTER VI"),
            source_title="Pierre Curie - The Discovery of Radium",
            source_slug="pierre_curie_discovery_of_radium",
            section="chapter_v_discovery_of_radium",
            source_type="biography",
        ),
        build_source_document(
            "agt_009",
            extract_heading_section(autobiographical_notes_body, "CHAPTER II", "CHAPTER III"),
            source_title="Autobiographical Notes - Discovery and Old Shed Years",
            source_slug="autobiographical_notes_discovery_old_shed_years",
            section="autobiographical_notes_chapter_ii",
            source_type="autobiography",
        ),
        build_source_document(
            "agt_009",
            extract_heading_section(autobiographical_notes_body, "CHAPTER III", "CHAPTER IV"),
            source_title="Autobiographical Notes - War Years",
            source_slug="autobiographical_notes_war_years",
            section="autobiographical_notes_chapter_iii",
            source_type="autobiography",
        ),
    ]


def extract_leonardo_source_documents(text: str) -> List[SourceDocument]:
    """Build the Leonardo source set from the selected notebook text."""
    return [build_source_document("agt_007", extract_thoughts_on_art_and_life_body(text))]


def extract_trotsky_source_documents(text: str) -> List[SourceDocument]:
    """Build the Trotsky source set from the cleaned memoir excerpt."""
    return [build_source_document("agt_011", extract_my_life_selected_body(text))]


def extract_nietzsche_source_documents(text: str) -> List[SourceDocument]:
    """Build the Nietzsche source set from the selected Twilight sections."""
    return [build_source_document("agt_012", extract_twilight_of_the_idols_selected_body(text))]


def extract_tesla_source_documents(text: str) -> List[SourceDocument]:
    """Build the Tesla source set from the extracted autobiography body."""
    return [build_source_document("agt_013", extract_my_inventions_body(text))]


def extract_marie_antoinette_source_documents_wrapper(text: str) -> List[SourceDocument]:
    """Build the Marie Antoinette source set from curated records and the cleaned Campan memoir."""
    return extract_marie_antoinette_source_documents(text)


def split_structured_sections(text: str, section_boundary_pattern: str) -> List[str]:
    """Split a structured document into sections keyed by a heading regex."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    boundary_regex: Pattern[str] = re.compile(section_boundary_pattern)
    sections: List[str] = []
    current_lines: List[str] = []

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped:
            if current_lines and current_lines[-1] != "":
                current_lines.append("")
            continue

        if current_lines and boundary_regex.match(stripped):
            section_text = clean_whitespace("\n".join(current_lines))
            if section_text:
                sections.append(section_text)
            current_lines = [stripped]
            continue

        current_lines.append(stripped)

    if current_lines:
        section_text = clean_whitespace("\n".join(current_lines))
        if section_text:
            sections.append(section_text)

    return sections


def extract_source_documents(agent_id: str, text: str) -> List[Dict[str, str]]:
    """Dispatch to the configured source-document extractor for the selected agent."""
    return get_agent_ingest_plan(agent_id).document_extractor(text)


def _joined_chunk_length(units: Sequence[str]) -> int:
    if not units:
        return 0

    return len("\n\n".join(units))


def _seed_overlap_units(unit_texts: Sequence[str], overlap_budget: int) -> List[str]:
    """Carry trailing units forward to preserve limited local continuity between chunks."""
    if overlap_budget <= 0:
        return []

    overlap_sections: List[str] = []
    consumed = 0

    for section in reversed(unit_texts):
        additional = len(section) if not overlap_sections else len(section) + 2
        if overlap_sections and consumed + additional > overlap_budget:
            break
        overlap_sections.insert(0, section)
        consumed += additional
        if consumed >= overlap_budget:
            break

    return overlap_sections


def _split_by_first_matching_boundary(text: str, boundary_patterns: Sequence[str]) -> List[str]:
    """Split by the first configured structural boundary that yields multiple sections."""
    for boundary_pattern in boundary_patterns:
        sections = split_structured_sections(text, boundary_pattern)
        if len(sections) > 1:
            return sections

    cleaned_text = clean_whitespace(text)
    return [cleaned_text] if cleaned_text else []


def _split_into_paragraphs(text: str) -> List[str]:
    return [clean_whitespace(segment) for segment in text.split("\n\n") if clean_whitespace(segment)]


def _split_into_sentences(text: str) -> List[str]:
    sentence_pattern = re.compile(r".+?(?:[.!?](?=\s+|$)|$)", re.DOTALL)
    sentences = [clean_whitespace(match.group(0)) for match in sentence_pattern.finditer(text)]
    return [sentence for sentence in sentences if sentence]


def _hard_slice_text(text: str, max_chunk_size: int) -> List[str]:
    normalized = clean_whitespace(text)
    if not normalized:
        return []

    if len(normalized) <= max_chunk_size:
        return [normalized]

    pieces: List[str] = []
    remaining = normalized
    minimum_split = max(1, int(max_chunk_size * 0.6))

    while len(remaining) > max_chunk_size:
        split_at = remaining.rfind(" ", minimum_split, max_chunk_size + 1)
        if split_at == -1:
            split_at = remaining.find(" ", max_chunk_size)
        if split_at == -1:
            split_at = max_chunk_size

        piece = remaining[:split_at].strip()
        if piece:
            pieces.append(piece)
        remaining = remaining[split_at:].strip()

    if remaining:
        pieces.append(remaining)

    return pieces


def _expand_text_to_units(text: str, policy: ChunkingPolicy) -> List[str]:
    """Refine text into reusable units using boundary-first splitting."""
    def refine_to_sentence_or_slice(unit_text: str) -> List[str]:
        normalized = clean_whitespace(unit_text)
        if not normalized:
            return []
        if len(normalized) <= policy.target_chunk_size:
            return [normalized]

        sentences = _split_into_sentences(normalized)
        if len(sentences) <= 1:
            return _hard_slice_text(normalized, policy.target_chunk_size)

        refined: List[str] = []
        for sentence in sentences:
            if len(sentence) <= policy.target_chunk_size:
                refined.append(sentence)
            else:
                refined.extend(_hard_slice_text(sentence, policy.target_chunk_size))
        return refined


    structural_sections = _split_by_first_matching_boundary(text, policy.boundary_patterns)
    refined_units: List[str] = []

    for section in structural_sections:
        normalized_section = clean_whitespace(section)
        if not normalized_section:
            continue
        if len(normalized_section) <= policy.target_chunk_size:
            refined_units.append(normalized_section)
            continue

        paragraphs = _split_into_paragraphs(normalized_section)
        if len(paragraphs) <= 1:
            refined_units.extend(refine_to_sentence_or_slice(normalized_section))
            continue

        for paragraph in paragraphs:
            if len(paragraph) <= policy.target_chunk_size:
                refined_units.append(paragraph)
            else:
                refined_units.extend(refine_to_sentence_or_slice(paragraph))

    return refined_units


def _assemble_chunks(units: Sequence[str], policy: ChunkingPolicy) -> List[str]:
    """Pack refined units into chunks near the target size with percentage-based overlap."""
    chunks: List[str] = []
    current_units: List[str] = []

    for unit in units:
        normalized_unit = clean_whitespace(unit)
        if not normalized_unit:
            continue

        candidate_units = [*current_units, normalized_unit]
        candidate_length = _joined_chunk_length(candidate_units)
        if current_units and candidate_length > policy.target_chunk_size:
            finalized = clean_whitespace("\n\n".join(current_units))
            if finalized:
                chunks.append(finalized)

            overlap_budget = int(round(len(finalized) * (policy.overlap_percent / 100.0)))
            current_units = _seed_overlap_units(current_units, overlap_budget)

            if current_units and _joined_chunk_length([*current_units, normalized_unit]) > policy.target_chunk_size:
                current_units = []

        current_units.append(normalized_unit)

    if current_units:
        final_chunk = clean_whitespace("\n\n".join(current_units))
        if final_chunk:
            chunks.append(final_chunk)

    return chunks


def _is_heading_like(text: str) -> bool:
    normalized = clean_whitespace(text)
    if not normalized or len(normalized) > 140:
        return False

    if normalized.startswith("CHAPTER "):
        return True
    if re.match(r"^[IVXLC]+\.\s+[A-Z]", normalized):
        return True
    if re.match(r"^\d+$", normalized):
        return True
    if normalized.endswith(":") and len(normalized.split()) <= 12:
        return True
    if normalized == normalized.upper() and any(character.isalpha() for character in normalized):
        return True

    return False


def _merge_chunks(left: str, right: str) -> str:
    return clean_whitespace(f"{left}\n\n{right}")


def _max_merged_chunk_size(policy: ChunkingPolicy) -> int:
    return max(policy.target_chunk_size, int(round(policy.target_chunk_size * policy.max_merge_ratio)))


def _rebalance_small_chunks(chunks: Sequence[str], policy: ChunkingPolicy) -> List[str]:
    """Merge undersized chunks into their closest viable neighbor within the configured merge cap."""
    max_chunk_size = _max_merged_chunk_size(policy)
    pending = [clean_whitespace(chunk) for chunk in chunks if clean_whitespace(chunk)]
    rebalanced: List[str] = []
    index = 0

    while index < len(pending):
        current = pending[index]
        if len(current) < policy.min_chunk_chars:
            if rebalanced:
                merged_with_previous = _merge_chunks(rebalanced[-1], current)
                if len(merged_with_previous) <= max_chunk_size:
                    rebalanced[-1] = merged_with_previous
                    index += 1
                    continue

            if index + 1 < len(pending):
                merged_with_next = _merge_chunks(current, pending[index + 1])
                if len(merged_with_next) <= max_chunk_size:
                    rebalanced.append(merged_with_next)
                    index += 2
                    continue

        rebalanced.append(current)
        index += 1

    return rebalanced


def _merge_heading_chunks(chunks: Sequence[str], policy: ChunkingPolicy) -> List[str]:
    """Merge heading-only chunks into the following chunk after size rebalancing."""
    max_chunk_size = _max_merged_chunk_size(policy)
    merged_chunks: List[str] = []
    index = 0

    while index < len(chunks):
        current = chunks[index]
        if _is_heading_like(current) and index + 1 < len(chunks):
            merged_with_next = _merge_chunks(current, chunks[index + 1])
            if len(merged_with_next) <= max_chunk_size:
                merged_chunks.append(merged_with_next)
                index += 2
                continue

        merged_chunks.append(current)
        index += 1

    return merged_chunks


def _drop_undersized_chunks(chunks: Sequence[str], policy: ChunkingPolicy) -> List[str]:
    """Discard any residual fragment that remains below the minimum after merge attempts."""
    normalized_chunks = [clean_whitespace(chunk) for chunk in chunks if clean_whitespace(chunk)]
    if len(normalized_chunks) <= 1:
        return normalized_chunks

    return [chunk for chunk in normalized_chunks if len(chunk) >= policy.min_chunk_chars]


def chunk_with_policy(text: str, policy: ChunkingPolicy) -> List[str]:
    """Apply the shared boundary-first chunking pipeline for one speaker policy."""
    units = _expand_text_to_units(text, policy)
    chunks = _assemble_chunks(units, policy)
    chunks = _rebalance_small_chunks(chunks, policy)
    chunks = _merge_heading_chunks(chunks, policy)
    chunks = _rebalance_small_chunks(chunks, policy)
    return _drop_undersized_chunks(chunks, policy)


def _resolve_chunking_policy(
    plan: AgentIngestPlan,
    *,
    chunk_size: Optional[int] = None,
    overlap_percent: Optional[int] = None,
    legacy_chunk_overlap: Optional[int] = None,
) -> ChunkingPolicy:
    """Create an effective policy, honoring operator overrides while preserving per-agent defaults."""
    target_chunk_size = max(1, chunk_size or plan.chunking_policy.target_chunk_size)
    effective_overlap_percent = overlap_percent
    if effective_overlap_percent is None and legacy_chunk_overlap is not None:
        effective_overlap_percent = int(round((max(0, legacy_chunk_overlap) / max(1, target_chunk_size)) * 100))

    if effective_overlap_percent is None:
        effective_overlap_percent = plan.chunking_policy.overlap_percent

    return ChunkingPolicy(
        target_chunk_size=target_chunk_size,
        overlap_percent=max(0, min(50, effective_overlap_percent)),
        min_chunk_chars=min(plan.chunking_policy.min_chunk_chars, max(1, int(round(target_chunk_size * 0.6)))),
        max_merge_ratio=plan.chunking_policy.max_merge_ratio,
        boundary_patterns=plan.chunking_policy.boundary_patterns,
    )


AGENT_INGEST_PLANS: Dict[str, AgentIngestPlan] = {
    "agt_001": AgentIngestPlan(
        speaker_name="Socrates",
        extraction_summary="Extract the Apology and Crito bodies from a shared Project Gutenberg source file.",
        chunking_summary="Use boundary-first paragraph and sentence chunking with dialogue-sized chunks and light overlap.",
        document_extractor=extract_socrates_source_documents,
        chunking_policy=ChunkingPolicy(900, 12, 60, 1.2, ()),
    ),
    "agt_014": AgentIngestPlan(
        speaker_name="Marie Antoinette",
        extraction_summary=(
            "Extract the five curated front-matter documents from the hybrid corpus and append a cleaned Project Gutenberg body of Madame Campan's memoirs, "
            "excluding illustration lists and license boilerplate."
        ),
        chunking_summary=(
            "Use paragraph-first chunking so letters, anecdotes, legal accusations, and memoir scenes stay intact without mid-sentence breaks."
        ),
        document_extractor=extract_marie_antoinette_source_documents_wrapper,
        chunking_policy=ChunkingPolicy(950, 12, 60, 1.2, ()),
    ),
    "agt_002": AgentIngestPlan(
        speaker_name="Steve Jobs",
        extraction_summary="Split the file into a leading Stanford speech plus any later dash-delimited interviews, keynotes, or letters.",
        chunking_summary="Use paragraph-first chunking across each extracted source document with moderate overlap for speech and interview continuity.",
        document_extractor=extract_jobs_source_documents,
        chunking_policy=ChunkingPolicy(950, 15, 60, 1.2, ()),
    ),
    "agt_003": AgentIngestPlan(
        speaker_name="Sun Tzu",
        extraction_summary="Keep the handbook body starting at Chapter I and strip the Project Gutenberg footer.",
        chunking_summary="Chunk on chapter and numbered section boundaries before falling back to paragraphs and sentences.",
        document_extractor=extract_sun_tzu_source_documents,
        chunking_policy=ChunkingPolicy(900, 15, 60, 1.2, (r"^Chapter\s+[IVXLC]+\.", r"^\d+(?:,\s*\d+)?\.")),
    ),
    "agt_004": AgentIngestPlan(
        speaker_name="Napoleon Bonaparte",
        extraction_summary=(
            "Extract exact case-insensitive Napoleon anchor windows from all four memoir volumes, "
            "keeping 3 paragraphs before and 5 after each matched heading or phrase."
        ),
        chunking_summary=(
            "Use paragraph-first chunking on each extracted anchor window so campaign, legal, and "
            "pan-European reflections remain grouped with their immediate context."
        ),
        document_extractor=extract_napoleon_source_documents_wrapper,
        chunking_policy=ChunkingPolicy(950, 12, 60, 1.2, ()),
    ),
    "agt_005": AgentIngestPlan(
        speaker_name="Marcus Aurelius",
        extraction_summary="Select the Second and Fourth books from the configured source text.",
        chunking_summary="Use compact paragraph-first chunking tuned for short meditative fragments.",
        document_extractor=extract_meditations_source_documents,
        chunking_policy=ChunkingPolicy(400, 10, 60, 1.2, ()),
    ),
    "agt_006": AgentIngestPlan(
        speaker_name="Cleopatra",
        extraction_summary=(
            "Extract the contiguous Cleopatra arc from Plutarch's Life of Antony, "
            "starting at Antony's infatuation and ending before the children-and-legacy epilogue."
        ),
        chunking_summary=(
            "Use paragraph-first chunking across the filtered Cleopatra narrative so diplomacy, Actium, "
            "and the death sequence remain in contiguous prose blocks."
        ),
        document_extractor=extract_cleopatra_source_documents,
        chunking_policy=ChunkingPolicy(900, 15, 60, 1.2, ()),
    ),
    "agt_007": AgentIngestPlan(
        speaker_name="Leonardo da Vinci",
        extraction_summary="Keep the main Thoughts on Life body and stop before bibliography and reference appendices.",
        chunking_summary="Use paragraph-first chunking for notebook-style fragments without forcing artificial structural bands.",
        document_extractor=extract_leonardo_source_documents,
        chunking_policy=ChunkingPolicy(500, 10, 60, 1.2, ()),
    ),
    "agt_008": AgentIngestPlan(
        speaker_name="Ada Lovelace",
        extraction_summary=(
            "Extract only Note A and Note G from Lovelace's Analytical Engine notes, render standalone formulas as LaTeX, "
            "and replace diagram or table-heavy blocks with structured prose summaries."
        ),
        chunking_summary=(
            "Use note-aware paragraph chunking so Lovelace's conceptual explanations, philosophical claims, and engine-capability prose "
            "stay grouped under their note boundaries."
        ),
        document_extractor=extract_lovelace_source_documents,
        chunking_policy=ChunkingPolicy(900, 12, 60, 1.2, (r"^NOTE [A-G]",)),
    ),
    "agt_009": AgentIngestPlan(
        speaker_name="Marie Curie",
        extraction_summary=(
            "Extract the requested Marie Curie narratives from the Pierre Curie omnibus: "
            "the discovery-of-radium chapter plus the autobiographical old-shed and war-years chapters."
        ),
        chunking_summary=(
            "Use paragraph-first chunking across each selected Curie chapter so the discovery narrative "
            "and wartime reflections stay in coherent prose blocks."
        ),
        document_extractor=extract_curie_source_documents,
        chunking_policy=ChunkingPolicy(950, 15, 60, 1.2, ()),
    ),
    "agt_011": AgentIngestPlan(
        speaker_name="Leon Trotsky",
        extraction_summary="Remove duplicated site-navigation noise, then keep the selected chapter body beginning at the first chapter heading.",
        chunking_summary="Chunk on chapter boundaries so memoir context stays grouped by chapter before paragraph and sentence fallback.",
        document_extractor=extract_trotsky_source_documents,
        chunking_policy=ChunkingPolicy(1000, 15, 60, 1.2, (r"^CHAPTER\s+[IVXLC]+",)),
    ),
    "agt_012": AgentIngestPlan(
        speaker_name="Friedrich Nietzsche",
        extraction_summary="Extract the selected Twilight of the Idols sections configured for the current corpus.",
        chunking_summary="Use compact boundary-first chunking that prioritizes section headings and numbered aphorisms before sentence fallback.",
        document_extractor=extract_nietzsche_source_documents,
        chunking_policy=ChunkingPolicy(400, 12, 60, 1.2, (r"^[A-Z0-9 “”—'’,:;!?().\-]+$", r"^\d+$")),
    ),
    "agt_013": AgentIngestPlan(
        speaker_name="Nikola Tesla",
        extraction_summary="Keep the My Inventions body from the first roman-numeral section through the public-domain footer boundary.",
        chunking_summary="Chunk on roman-numeral section headings before paragraph and sentence fallback.",
        document_extractor=extract_tesla_source_documents,
        chunking_policy=ChunkingPolicy(950, 15, 60, 1.2, (r"^[IVXLC]+\.\s",)),
    ),
}


def get_agent_ingest_plan(agent_id: str) -> AgentIngestPlan:
    """Return the configured ingestion plan for an agent or fail fast."""
    if agent_id not in AGENT_INGEST_PLANS:
        raise ValueError(f"Unsupported agent id: {agent_id}")

    return AGENT_INGEST_PLANS[agent_id]


def format_agent_plan(agent_id: str) -> str:
    """Render a human-readable summary of one agent's ingestion plan."""
    plan = get_agent_ingest_plan(agent_id)
    source_path = resolve_source_path(agent_id, None)
    policy = plan.chunking_policy

    return "\n".join(
        [
            f"Agent: {agent_id}",
            f"Speaker: {plan.speaker_name}",
            f"Default source file: {source_path.name}",
            f"Source extraction: {plan.extraction_summary}",
            f"Chunking: {plan.chunking_summary}",
            (
                "Chunking policy: "
                f"target={policy.target_chunk_size}, overlap={policy.overlap_percent}%, "
                f"min={policy.min_chunk_chars}, max_merge_ratio={policy.max_merge_ratio}, "
                f"boundaries={len(policy.boundary_patterns)}"
            ),
        ]
    )


def format_agent_plan_catalog() -> str:
    """Render the supported ingestion-plan catalog for CLI inspection."""
    lines = ["Supported speaker ingestion plans:"]

    for agent_id, plan in sorted(AGENT_INGEST_PLANS.items()):
        lines.append(f"- {agent_id}: {plan.speaker_name}")

    return "\n".join(lines)


def chunk_source_text(
    agent_id: str,
    text: str,
    *,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
    overlap_percent: Optional[int] = None,
) -> List[str]:
    """Chunk a source document using the shared policy-driven pipeline for its agent."""
    plan = get_agent_ingest_plan(agent_id)
    effective_policy = _resolve_chunking_policy(
        plan,
        chunk_size=chunk_size,
        overlap_percent=overlap_percent,
        legacy_chunk_overlap=chunk_overlap,
    )
    return chunk_with_policy(text, effective_policy)


def build_chunk_payloads(
    *,
    agent_id: str,
    source_path: Path,
    source_document: Dict[str, str],
    chunks: List[str],
) -> List[Dict[str, object]]:
    """Build Upstash Vector payloads with stable ids and source metadata."""
    payloads: List[Dict[str, object]] = []
    for index, chunk in enumerate(chunks, start=1):
        payloads.append(
            {
                "id": f"{agent_id}:{source_document['source_slug']}:{index:04d}",
                "data": chunk,
                "metadata": {
                    "agent_id": agent_id,
                    "speaker_name": source_document["speaker_name"],
                    "source_title": source_document["source_title"],
                    "author": source_document["author"],
                    "translator": source_document["translator"],
                    "source_type": source_document["source_type"],
                    "voice_type": source_document["voice_type"],
                    "section": source_document["section"],
                    "source_slug": source_document["source_slug"],
                    "chunk_index": index,
                    "source_file": str(source_path.name),
                },
            }
        )

    return payloads


def upsert_chunks(vectors: List[Dict[str, object]], *, namespace: str) -> None:
    """Write prepared chunk payloads to Upstash Vector, optionally within a namespace."""
    if not UPSTASH_VECTOR_REST_URL or not UPSTASH_VECTOR_REST_TOKEN:
        raise ValueError("Missing UPSTASH_VECTOR_REST_URL or UPSTASH_VECTOR_REST_TOKEN in environment")

    from upstash_vector import Index

    index = Index(url=UPSTASH_VECTOR_REST_URL, token=UPSTASH_VECTOR_REST_TOKEN)
    for start_index in range(0, len(vectors), UPSTASH_VECTOR_MAX_BATCH_SIZE):
        batch = vectors[start_index : start_index + UPSTASH_VECTOR_MAX_BATCH_SIZE]
        if namespace:
            index.upsert(vectors=batch, namespace=namespace)
            continue

        index.upsert(vectors=batch)


def _safe_console_text(value: object) -> str:
    """Render terminal preview text safely on shells that are not UTF-8 configured."""
    text = str(value)
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding, errors="replace")


def main() -> None:
    """Run ingestion or plan-inspection mode based on the provided CLI arguments."""
    args = parse_args()
    if args.list_agents:
        print(format_agent_plan_catalog())
        if not args.describe_agent:
            return

    if args.describe_agent:
        print(format_agent_plan(args.describe_agent))
        return

    plan = get_agent_ingest_plan(args.agent_id)

    source_path = resolve_source_path(args.agent_id, args.source_file)
    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found: {source_path}")

    raw_text = source_path.read_text(encoding="utf-8")
    source_documents = extract_source_documents(args.agent_id, raw_text)
    payloads: List[Dict[str, object]] = []
    source_summaries: List[str] = []
    effective_policy = _resolve_chunking_policy(
        plan,
        chunk_size=max(60, args.chunk_size) if args.chunk_size is not None else None,
        overlap_percent=args.overlap_percent,
        legacy_chunk_overlap=args.chunk_overlap,
    )

    for source_document in source_documents:
        chunks = chunk_source_text(
            args.agent_id,
            source_document["text"],
            chunk_size=effective_policy.target_chunk_size,
            overlap_percent=effective_policy.overlap_percent,
        )
        payloads.extend(
            build_chunk_payloads(
                agent_id=args.agent_id,
                source_path=source_path,
                source_document=source_document,
                chunks=chunks,
            )
        )
        source_summaries.append(
            f"- {source_document['source_title']}: {len(chunks)} chunks, avg length "
            f"{(sum(len(chunk) for chunk in chunks) / len(chunks)):.1f}" if chunks else f"- {source_document['source_title']}: 0 chunks"
        )

    print(f"Speaker: {plan.speaker_name}")
    print(f"Source extraction: {plan.extraction_summary}")
    print(f"Chunking: {plan.chunking_summary}")
    print(
        "Effective chunking policy: "
        f"target={effective_policy.target_chunk_size}, overlap={effective_policy.overlap_percent}%, "
        f"min={effective_policy.min_chunk_chars}, max_merge_ratio={effective_policy.max_merge_ratio}"
    )
    print(f"Prepared {len(payloads)} chunks for {args.agent_id} from {source_path.name}")
    if source_summaries:
        print("Source breakdown:")
        for summary in source_summaries:
            print(summary)
    if payloads:
        preview = payloads[0]["data"]
        print("First chunk preview:\n")
        print(_safe_console_text(str(preview)[:700]))
        print("\n---")

    if args.dry_run:
        print("Dry run only; no data was written to Upstash Vector.")
        return

    upsert_chunks(payloads, namespace=args.namespace)
    print("Upsert complete.")


if __name__ == "__main__":
    main()