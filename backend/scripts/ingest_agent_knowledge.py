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
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Pattern

from dotenv import load_dotenv


SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
REPO_ROOT = BACKEND_DIR.parent

load_dotenv(REPO_ROOT / ".env")

UPSTASH_VECTOR_REST_URL = os.environ.get("UPSTASH_VECTOR_REST_URL")
UPSTASH_VECTOR_REST_TOKEN = os.environ.get("UPSTASH_VECTOR_REST_TOKEN")


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
    }
}

SourceDocument = Dict[str, str]


@dataclass(frozen=True)
class AgentIngestPlan:
    speaker_name: str
    extraction_summary: str
    chunking_summary: str
    document_extractor: Callable[[str], List[SourceDocument]]
    chunker: Callable[[str, int, int], List[str]]


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
    parser.add_argument("--chunk-size", type=int, default=1200, help="Target chunk size in characters")
    parser.add_argument("--chunk-overlap", type=int, default=200, help="Overlap size in characters")
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


def _seed_overlap_sections(section_texts: List[str], overlap_budget: int) -> List[str]:
    """Carry trailing sections forward when structured chunkers need overlap context."""
    if overlap_budget <= 0:
        return []

    overlap_sections: List[str] = []
    consumed = 0

    for section in reversed(section_texts):
        additional = len(section) if not overlap_sections else len(section) + 2
        if overlap_sections and consumed + additional > overlap_budget:
            break
        overlap_sections.insert(0, section)
        consumed += additional
        if consumed >= overlap_budget:
            break

    return overlap_sections


def chunk_handbook_text(text: str, *, chunk_size: int, chunk_overlap: int) -> List[str]:
    """Chunk handbook-style texts on chapter and numbered subsection boundaries."""
    return chunk_structured_text(
        text,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        section_boundary_pattern=r"^(Chapter\s+[IVXLC]+\.|\d+(?:,\s*\d+)?\.)",
    )


def chunk_structured_text(
    text: str,
    *,
    chunk_size: int,
    chunk_overlap: int,
    section_boundary_pattern: str,
) -> List[str]:
    """Chunk sectioned texts while preserving major section boundaries when possible."""
    sections = split_structured_sections(text, section_boundary_pattern)

    chunks: List[str] = []
    current_sections: List[str] = []
    current_length = 0

    for section in sections:
        section_length = len(section)
        separator_length = 2 if current_sections else 0

        if current_sections and current_length + separator_length + section_length > chunk_size:
            chunks.append(clean_whitespace("\n\n".join(current_sections)))
            current_sections = _seed_overlap_sections(current_sections, chunk_overlap)
            current_length = len("\n\n".join(current_sections)) if current_sections else 0
            separator_length = 2 if current_sections else 0

        if section_length > chunk_size:
            if current_sections:
                chunks.append(clean_whitespace("\n\n".join(current_sections)))
                current_sections = []
                current_length = 0

            for paragraph_chunk in chunk_text(section, chunk_size=chunk_size, chunk_overlap=chunk_overlap):
                if paragraph_chunk:
                    chunks.append(paragraph_chunk)
            continue

        current_sections.append(section)
        current_length += separator_length + section_length

    if current_sections:
        chunks.append(clean_whitespace("\n\n".join(current_sections)))

    return [chunk for chunk in chunks if chunk]


def chunk_banded_structured_text(
    text: str,
    *,
    min_chunk_size: int,
    max_chunk_size: int,
    section_boundary_pattern: str,
) -> List[str]:
    """Chunk aphoristic texts into bounded bands without over-fragmenting short sections."""
    sections = split_structured_sections(text, section_boundary_pattern)

    def split_long_section(section: str) -> List[str]:
        sentences = re.split(r"(?<=[.!?])\s+", section)
        sentence_chunks: List[str] = []
        current = ""

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            candidate = sentence if not current else f"{current} {sentence}"
            if len(candidate) <= max_chunk_size:
                current = candidate
                continue

            if current:
                sentence_chunks.append(clean_whitespace(current))
                current = sentence
            else:
                for index in range(0, len(sentence), max_chunk_size):
                    sentence_chunks.append(clean_whitespace(sentence[index:index + max_chunk_size]))
                current = ""

        if current:
            sentence_chunks.append(clean_whitespace(current))

        if len(sentence_chunks) >= 2 and len(sentence_chunks[-1]) < min_chunk_size:
            merged = clean_whitespace(f"{sentence_chunks[-2]} {sentence_chunks[-1]}")
            if len(merged) <= max_chunk_size:
                sentence_chunks[-2] = merged
                sentence_chunks.pop()

        return [chunk for chunk in sentence_chunks if chunk]

    chunks: List[str] = []
    current_sections: List[str] = []
    current_length = 0

    for section in sections:
        if len(section) > max_chunk_size:
            if current_sections:
                chunks.append(clean_whitespace("\n\n".join(current_sections)))
                current_sections = []
                current_length = 0

            chunks.extend(split_long_section(section))
            continue

        current_text = clean_whitespace("\n\n".join(current_sections)) if current_sections else ""
        candidate = section if not current_sections else f"{current_text}\n\n{section}"
        candidate_length = len(candidate)

        if current_sections and candidate_length > max_chunk_size:
            chunks.append(clean_whitespace("\n\n".join(current_sections)))
            current_sections = [section]
            current_length = len(section)
            continue

        current_sections.append(section)
        current_length = candidate_length

        if current_length >= min_chunk_size:
            chunks.append(clean_whitespace("\n\n".join(current_sections)))
            current_sections = []
            current_length = 0

    if current_sections:
        trailing = clean_whitespace("\n\n".join(current_sections))
        if chunks and len(trailing) < min_chunk_size:
            merged = clean_whitespace(f"{chunks[-1]}\n\n{trailing}")
            if len(merged) <= max_chunk_size:
                chunks[-1] = merged
            else:
                chunks.append(trailing)
        else:
            chunks.append(trailing)

    normalized_chunks = [chunk for chunk in chunks if chunk]
    rebalanced_chunks: List[str] = []
    index = 0

    while index < len(normalized_chunks):
        current = normalized_chunks[index]

        if len(current) < min_chunk_size and index + 1 < len(normalized_chunks):
            merged_with_next = clean_whitespace(f"{current}\n\n{normalized_chunks[index + 1]}")
            if len(merged_with_next) <= max_chunk_size:
                rebalanced_chunks.append(merged_with_next)
                index += 2
                continue

        if rebalanced_chunks and len(current) < min_chunk_size:
            merged_with_previous = clean_whitespace(f"{rebalanced_chunks[-1]}\n\n{current}")
            if len(merged_with_previous) <= max_chunk_size:
                rebalanced_chunks[-1] = merged_with_previous
                index += 1
                continue

        rebalanced_chunks.append(current)
        index += 1

    return rebalanced_chunks


def chunk_default_strategy(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    """Apply the default paragraph-and-sentence chunking strategy."""
    return chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)


def chunk_sun_tzu_strategy(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    """Apply the Sun Tzu handbook chunking strategy."""
    return chunk_handbook_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)


def chunk_trotsky_strategy(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    """Apply the Trotsky chapter-aware chunking strategy."""
    return chunk_structured_text(
        text,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        section_boundary_pattern=r"^CHAPTER\s+[IVXLC]+",
    )


def chunk_nietzsche_strategy(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    """Apply the Nietzsche banded aphorism chunking strategy."""
    min_chunk_size = max(300, chunk_size - 60)
    max_chunk_size = max(min_chunk_size, chunk_size + 40)
    return chunk_banded_structured_text(
        text,
        min_chunk_size=min_chunk_size,
        max_chunk_size=max_chunk_size,
        section_boundary_pattern=r"^\d+$",
    )


def chunk_tesla_strategy(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    """Apply the Tesla roman-numeral section chunking strategy."""
    return chunk_structured_text(
        text,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        section_boundary_pattern=r"^[IVXLC]+\.\s",
    )


AGENT_INGEST_PLANS: Dict[str, AgentIngestPlan] = {
    "agt_001": AgentIngestPlan(
        speaker_name="Socrates",
        extraction_summary="Extract the Apology and Crito bodies from a shared Project Gutenberg source file.",
        chunking_summary="Use default paragraph and sentence chunking because the dialogue reads cleanly without custom section bands.",
        document_extractor=extract_socrates_source_documents,
        chunker=chunk_default_strategy,
    ),
    "agt_002": AgentIngestPlan(
        speaker_name="Steve Jobs",
        extraction_summary="Split the file into a leading Stanford speech plus any later dash-delimited interviews, keynotes, or letters.",
        chunking_summary="Use default paragraph and sentence chunking across each extracted source document.",
        document_extractor=extract_jobs_source_documents,
        chunker=chunk_default_strategy,
    ),
    "agt_003": AgentIngestPlan(
        speaker_name="Sun Tzu",
        extraction_summary="Keep the handbook body starting at Chapter I and strip the Project Gutenberg footer.",
        chunking_summary="Chunk on chapter and numbered section boundaries so each vector keeps strategic units intact.",
        document_extractor=extract_sun_tzu_source_documents,
        chunker=chunk_sun_tzu_strategy,
    ),
    "agt_005": AgentIngestPlan(
        speaker_name="Marcus Aurelius",
        extraction_summary="Select the Second and Fourth books from the configured source text.",
        chunking_summary="Use default paragraph chunking because each selected book is already aphoristic and compact.",
        document_extractor=extract_meditations_source_documents,
        chunker=chunk_default_strategy,
    ),
    "agt_007": AgentIngestPlan(
        speaker_name="Leonardo da Vinci",
        extraction_summary="Keep the main Thoughts on Life body and stop before bibliography and reference appendices.",
        chunking_summary="Use default paragraph chunking for notebook-style fragments.",
        document_extractor=extract_leonardo_source_documents,
        chunker=chunk_default_strategy,
    ),
    "agt_011": AgentIngestPlan(
        speaker_name="Leon Trotsky",
        extraction_summary="Remove duplicated site-navigation noise, then keep the selected chapter body beginning at the first chapter heading.",
        chunking_summary="Chunk on chapter boundaries so memoir context stays grouped by chapter.",
        document_extractor=extract_trotsky_source_documents,
        chunker=chunk_trotsky_strategy,
    ),
    "agt_012": AgentIngestPlan(
        speaker_name="Friedrich Nietzsche",
        extraction_summary="Extract the selected Twilight of the Idols sections configured for the current corpus.",
        chunking_summary="Use banded structured chunking to keep numbered aphorism groups near the target size without over-fragmenting them.",
        document_extractor=extract_nietzsche_source_documents,
        chunker=chunk_nietzsche_strategy,
    ),
    "agt_013": AgentIngestPlan(
        speaker_name="Nikola Tesla",
        extraction_summary="Keep the My Inventions body from the first roman-numeral section through the public-domain footer boundary.",
        chunking_summary="Chunk on roman-numeral section headings so each autobiographical movement stays coherent.",
        document_extractor=extract_tesla_source_documents,
        chunker=chunk_tesla_strategy,
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

    return "\n".join(
        [
            f"Agent: {agent_id}",
            f"Speaker: {plan.speaker_name}",
            f"Default source file: {source_path.name}",
            f"Source extraction: {plan.extraction_summary}",
            f"Chunking: {plan.chunking_summary}",
        ]
    )


def format_agent_plan_catalog() -> str:
    """Render the supported ingestion-plan catalog for CLI inspection."""
    lines = ["Supported speaker ingestion plans:"]

    for agent_id, plan in sorted(AGENT_INGEST_PLANS.items()):
        lines.append(f"- {agent_id}: {plan.speaker_name}")

    return "\n".join(lines)


def chunk_source_text(agent_id: str, text: str, *, chunk_size: int, chunk_overlap: int) -> List[str]:
    """Chunk a source document using the strategy configured for its agent."""
    plan = get_agent_ingest_plan(agent_id)
    return plan.chunker(text, chunk_size, chunk_overlap)


def chunk_text(text: str, *, chunk_size: int, chunk_overlap: int) -> List[str]:
    """Chunk free-form text by paragraphs first, then by sentences when needed."""
    paragraphs = [segment.strip() for segment in text.split("\n\n") if segment.strip()]
    if len(paragraphs) >= 2:
        first_paragraph = paragraphs[0]
        if len(first_paragraph) < 160 and (
            "\n" in first_paragraph
            or first_paragraph.startswith("CHAPTER")
            or re.match(r"^[IVXLC]+\.\s", first_paragraph)
            or re.match(r"^[A-Z0-9 ,;:'’\-\"()]+$", first_paragraph)
        ):
            paragraphs = [f"{first_paragraph}\n\n{paragraphs[1]}", *paragraphs[2:]]

    chunks: List[str] = []
    current = ""

    for paragraph in paragraphs:
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= chunk_size:
            current = candidate
            continue

        if current:
            chunks.append(current)

        if len(paragraph) <= chunk_size:
            current = paragraph
            continue

        sentence_parts = re.split(r"(?<=[.!?])\s+", paragraph)
        current = ""
        for sentence in sentence_parts:
            sentence = sentence.strip()
            if not sentence:
                continue

            candidate = sentence if not current else f"{current} {sentence}"
            if len(candidate) <= chunk_size:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                current = sentence

        if current and len(current) > chunk_size:
            for index in range(0, len(current), max(1, chunk_size - chunk_overlap)):
                chunks.append(current[index:index + chunk_size].strip())
            current = ""

    if current:
        chunks.append(current)

    normalized_chunks: List[str] = []
    for chunk in chunks:
        chunk = clean_whitespace(chunk)
        if chunk:
            normalized_chunks.append(chunk)

    return normalized_chunks


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
    if namespace:
        index.upsert(vectors=vectors, namespace=namespace)
        return

    index.upsert(vectors=vectors)


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

    chunk_size = max(200, args.chunk_size)
    chunk_overlap = max(0, min(args.chunk_overlap, args.chunk_size // 2))

    for source_document in source_documents:
        chunks = chunk_source_text(
            args.agent_id,
            source_document["text"],
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
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
    print(f"Prepared {len(payloads)} chunks for {args.agent_id} from {source_path.name}")
    if source_summaries:
        print("Source breakdown:")
        for summary in source_summaries:
            print(summary)
    if payloads:
        preview = payloads[0]["data"]
        print("First chunk preview:\n")
        print(str(preview)[:700])
        print("\n---")

    if args.dry_run:
        print("Dry run only; no data was written to Upstash Vector.")
        return

    upsert_chunks(payloads, namespace=args.namespace)
    print("Upsert complete.")


if __name__ == "__main__":
    main()