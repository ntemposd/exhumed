from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from .text_metrics import clean_text_for_similarity

# Live vector filter threshold — matches DatabaseService._VECTOR_SCORE_THRESHOLD.
GROUNDING_SCORE_FLOOR = 0.60
GROUNDING_SCORE_CEILING = 1.0


def join_retrieval_context(matches: Sequence[Mapping[str, Any]]) -> str:
    """Concatenate retrieved chunk texts for persona alignment scoring."""
    parts: List[str] = []
    for match in matches:
        text = str(match.get("data") or "").strip()
        if text:
            parts.append(text)
    return "\n".join(parts)


def score_grounding(top_score: Optional[float], *, used: bool) -> float:
    """Normalize retrieval top_score from `[0.60, 1.0]` into `[0.0, 1.0]`."""
    if not used or top_score is None:
        return 0.0

    span = GROUNDING_SCORE_CEILING - GROUNDING_SCORE_FLOOR
    if span <= 0:
        return 0.0

    normalized = (float(top_score) - GROUNDING_SCORE_FLOOR) / span
    return round(max(0.0, min(1.0, normalized)), 4)


def score_persona(answer: str, context_text: str) -> float:
    """Jaccard similarity between the answer and retrieved speaker context."""
    if not answer or not context_text:
        return 0.0

    answer_words = clean_text_for_similarity(answer)
    context_words = clean_text_for_similarity(context_text)
    if not answer_words or not context_words:
        return 0.0

    intersection = len(answer_words & context_words)
    union = len(answer_words | context_words)
    if union == 0:
        return 0.0
    return round(intersection / union, 4)


def build_answer_eval_scores(
    *,
    answer: str,
    retrieval_context_text: str,
    top_score: Optional[float],
    used: bool,
    debate_entropy: float,
) -> Dict[str, float]:
    """Build the three-metric answer scoreboard for turn telemetry."""
    return {
        "grounding": score_grounding(top_score, used=used),
        "persona": score_persona(answer, retrieval_context_text),
        "debate": round(max(0.0, min(1.0, float(debate_entropy))), 4),
    }
