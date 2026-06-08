"""
Compare current Jaccard entropy vs bigram-enhanced Jaccard on realistic debate pairs.
Run: python backend/scripts/compare_entropy.py
"""
from __future__ import annotations

import re
import string


# ── Current implementation ────────────────────────────────────────────────────

def unigram_tokens(text: str) -> set[str]:
    t = text.lower()
    t = re.sub(f"[{re.escape(string.punctuation)}]", " ", t)
    return {w for w in t.split() if w.strip()}


def jaccard_entropy(text1: str, text2: str) -> float:
    s1, s2 = unigram_tokens(text1), unigram_tokens(text2)
    if not s1 or not s2:
        return 1.0
    return round(1.0 - len(s1 & s2) / len(s1 | s2), 4)


# ── Option A: bigram-enhanced ─────────────────────────────────────────────────

def bigram_tokens(text: str) -> set[str]:
    t = text.lower()
    t = re.sub(f"[{re.escape(string.punctuation)}]", " ", t)
    tokens = [w for w in t.split() if w.strip()]
    unigrams = set(tokens)
    bigrams = {f"{tokens[i]} {tokens[i+1]}" for i in range(len(tokens) - 1)}
    return unigrams | bigrams


def bigram_entropy(text1: str, text2: str) -> float:
    s1, s2 = bigram_tokens(text1), bigram_tokens(text2)
    if not s1 or not s2:
        return 1.0
    return round(1.0 - len(s1 & s2) / len(s1 | s2), 4)


# ── Test pairs ────────────────────────────────────────────────────────────────

PAIRS = [
    (
        "SYNONYM BLINDNESS — same idea, different words (bigrams should NOT help)",
        "Virtue requires examination of one's principles and a willingness to question received wisdom.",
        "Excellence demands rigorous scrutiny of one's standards and the courage to challenge inherited assumptions.",
    ),
    (
        "SHARED PHRASE — both use 'social contract' (bigrams SHOULD help)",
        "The social contract binds citizens to the state through mutual obligation and the surrender of certain freedoms.",
        "Any legitimate government rests on the social contract — without consent of the governed, authority is mere force.",
    ),
    (
        "SHARED PHRASE — both use 'free will' and 'moral responsibility'",
        "Free will is the foundation of moral responsibility; without it, praise and blame lose all meaning.",
        "If free will is an illusion, then moral responsibility collapses — punishment becomes mere deterrence, not justice.",
    ),
    (
        "ECHOING — nearly identical content (both implementations should show low entropy)",
        "Power corrupts those who wield it without restraint or accountability to higher principles.",
        "Power tends to corrupt those who exercise it without accountability or adherence to higher principles.",
    ),
    (
        "TRULY DIVERGENT — unrelated topics (both implementations should show high entropy)",
        "The calculus of fluxions reveals how quantities change continuously, opening a window into the laws of motion.",
        "The conquest of Egypt required neutralising the Ottoman threat while securing Mediterranean supply lines.",
    ),
    (
        "PARTIAL OVERLAP — share some vocabulary but different conclusions",
        "Justice demands that the strong protect the weak — power without virtue is tyranny.",
        "Justice is an arrangement of power. The strong naturally dominate; calling it tyranny changes nothing of substance.",
    ),
]


def run() -> None:
    width = 72
    print("=" * width)
    print("ENTROPY COMPARISON: Jaccard (unigrams) vs Bigram-enhanced Jaccard")
    print("=" * width)

    for label, t1, t2 in PAIRS:
        j = jaccard_entropy(t1, t2)
        b = bigram_entropy(t1, t2)
        delta = round(j - b, 4)
        direction = f"DOWN {delta:.4f} (bigrams lower = more overlap detected)" if delta > 0.001 else ("UP - bigrams HIGHER" if delta < -0.001 else "no change")

        print(f"\n{'-' * width}")
        print(f"Case: {label}")
        print(f"  A: {t1[:80]}...")
        print(f"  B: {t2[:80]}...")
        print(f"  Jaccard  : {j:.4f}")
        print(f"  Bigram   : {b:.4f}  {direction}")

    print(f"\n{'=' * width}")
    print("Verdict:")
    print("  Bigrams help when both responses share exact multi-word phrases.")
    print("  Bigrams do NOT help with synonyms or paraphrases (the main failure mode).")
    print("  The improvement is real but narrow.")


if __name__ == "__main__":
    run()
