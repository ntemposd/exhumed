from __future__ import annotations

import re
import string


def clean_text_for_similarity(text: str) -> set[str]:
    """Normalize text into a token set for lightweight lexical similarity checks."""
    normalized_text = text.lower()
    normalized_text = re.sub(f"[{re.escape(string.punctuation)}]", " ", normalized_text)
    return {word for word in normalized_text.split() if word.strip()}


def calculate_jaccard_entropy(text1: str, text2: str) -> float:
    """Convert Jaccard similarity into an entropy-style divergence score in `[0.0, 1.0]`."""
    if not text1 or not text2:
        return 0.0 if (not text1 and not text2) else 1.0

    words_text1 = clean_text_for_similarity(text1)
    words_text2 = clean_text_for_similarity(text2)

    if not words_text1 or not words_text2:
        return 1.0 if (words_text1 != words_text2) else 0.0

    intersection = len(words_text1 & words_text2)
    union = len(words_text1 | words_text2)
    jaccard_similarity = intersection / union if union else 0.0
    return round(1.0 - jaccard_similarity, 4)