from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PromptBudget:
    """Token-conscious defaults for llama-3.1-8b-instant (6K TPM on Groq free tier)."""

    retrieval_top_k: int = 4
    retrieval_weak_top_k_bonus: int = 1
    context_turn_limit: int = 4
    max_source_chunk_chars: int = 680
    max_context_turn_chars: int = 320
    debate_max_tokens: int = 384


def truncate_for_prompt(text: str, max_chars: int) -> str:
    """Trim long passages at a word boundary so prompts stay within budget."""
    normalized = str(text or "").strip()
    if max_chars <= 0 or len(normalized) <= max_chars:
        return normalized

    clipped = normalized[:max_chars].rstrip()
    if len(clipped) < len(normalized):
        sentence_break = max(clipped.rfind(". "), clipped.rfind("? "), clipped.rfind("! "))
        if sentence_break >= int(max_chars * 0.55):
            clipped = clipped[: sentence_break + 1].rstrip()
        else:
            clipped = re.sub(r"\s+\S*$", "", clipped).rstrip()

        if clipped and clipped != normalized:
            clipped = f"{clipped}…"

    return clipped
