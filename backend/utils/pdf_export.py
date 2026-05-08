from __future__ import annotations

import logging
import os
import tempfile
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from fpdf import FPDF
from fpdf.enums import XPos, YPos


PDF_FONT_SEARCH_PATHS = {
    "regular": [
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeui.ttf",
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "arial.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
    ],
    "bold": [
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeuib.ttf",
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "arialbd.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
    ],
    "italic": [
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeuii.ttf",
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "ariali.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Italic.ttf"),
    ],
}

PDF_TEXT_REPLACEMENTS = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2026": "...",
        "\u00a0": " ",
    }
)


def configure_pdf_fonts(pdf: FPDF, *, logger: Optional[logging.Logger] = None) -> str:
    """Register a Unicode-capable PDF font family when one is available on the host."""
    regular_font = next((path for path in PDF_FONT_SEARCH_PATHS["regular"] if path.exists()), None)
    bold_font = next((path for path in PDF_FONT_SEARCH_PATHS["bold"] if path.exists()), None)
    italic_font = next((path for path in PDF_FONT_SEARCH_PATHS["italic"] if path.exists()), None)

    if regular_font:
        pdf.add_font("TranscriptSans", style="", fname=str(regular_font))
        pdf.add_font("TranscriptSans", style="B", fname=str(bold_font or regular_font))
        pdf.add_font("TranscriptSans", style="I", fname=str(italic_font or regular_font))
        return "TranscriptSans"

    if logger is not None:
        logger.warning("No TTF font found for PDF export; falling back to Helvetica core font")
    return "Helvetica"


def sanitize_pdf_text(value: Any, *, unicode_font_active: bool) -> str:
    """Normalize transcript text so PDF output is safe for the selected font mode."""
    text = str(value or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = unicodedata.normalize("NFKC", text).translate(PDF_TEXT_REPLACEMENTS)
    text = "".join(
        character
        for character in text
        if character == "\n" or unicodedata.category(character) not in {"Cc", "Cf", "Cs", "Co", "Cn", "So"}
    )

    if unicode_font_active:
        return text

    return text.encode("latin-1", errors="replace").decode("latin-1")


def export_session_pdf(
    messages: Iterable[Dict[str, Any]],
    session_id: Any,
    *,
    logger: Optional[logging.Logger] = None,
) -> str:
    """Render a session transcript to a temporary PDF file and return its path."""
    normalized_messages = list(messages)
    if not normalized_messages:
        raise ValueError("Cannot export an empty transcript")

    pdf = FPDF()
    pdf.add_page()
    font_family = configure_pdf_fonts(pdf, logger=logger)
    unicode_font_active = font_family != "Helvetica"
    topic = sanitize_pdf_text(normalized_messages[0].get("topic", "N/A"), unicode_font_active=unicode_font_active)

    pdf.set_font(font_family, "B" if unicode_font_active else "", 16)
    pdf.cell(
        0,
        10,
        sanitize_pdf_text("EXHUMED - Discussion Session", unicode_font_active=unicode_font_active),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
        align="C",
    )

    pdf.set_font(font_family, "", 10)
    pdf.cell(
        0,
        5,
        sanitize_pdf_text(f"Session ID: {session_id}", unicode_font_active=unicode_font_active),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.cell(
        0,
        5,
        sanitize_pdf_text(f"Topic: {topic}", unicode_font_active=unicode_font_active),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.ln(5)

    for message in normalized_messages:
        agent_name = sanitize_pdf_text(
            message.get("display_name", message.get("agent_id", "Unknown")),
            unicode_font_active=unicode_font_active,
        )
        turn_number = sanitize_pdf_text(message.get("turn_number", "-"), unicode_font_active=unicode_font_active)
        created_at = sanitize_pdf_text(message.get("created_at", "Unknown"), unicode_font_active=unicode_font_active)
        text = sanitize_pdf_text(message.get("message", ""), unicode_font_active=unicode_font_active)

        pdf.set_font(font_family, "B" if unicode_font_active else "", 10)
        pdf.set_text_color(33, 87, 171)
        pdf.cell(0, 4, f"{agent_name} (Turn {turn_number})", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        pdf.set_font(font_family, "I" if unicode_font_active else "", 8)
        pdf.set_text_color(128, 128, 128)
        pdf.cell(0, 3, created_at, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        pdf.set_font(font_family, "", 9)
        pdf.set_text_color(0, 0, 0)
        pdf.multi_cell(0, 4, text)
        pdf.ln(2)

    pdf_path = os.path.join(tempfile.gettempdir(), f"exhumed_{session_id}.pdf")
    pdf.output(pdf_path)
    return pdf_path