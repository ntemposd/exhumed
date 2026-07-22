from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List

JUDGE_SYSTEM_PROMPT = """You are a strict evaluator for a historical-persona debate system.
Score the candidate answer on two dimensions using integers 1-5.
Return ONLY valid JSON with this exact shape:
{
  "faithfulness": <1-5>,
  "persona": <1-5>,
  "faithfulness_notes": "<short reason>",
  "persona_notes": "<short reason>",
  "unsupported_claims": ["<claim>", "..."]
}

Faithfulness rubric:
5 = nearly all substantive claims are supported by the retrieved context
4 = mostly supported; minor unsupported flourish
3 = mixed; some important claims lack support
2 = largely unsupported or invents material
1 = ignores sources / fabricates freely
If retrieved context is empty: score at most 2 unless the answer clearly hedges or abstains from source-backed claims.

Persona rubric:
5 = strongly sounds like the named figure (voice, values, rhetorical style, era-appropriate reasoning)
4 = clearly in character with small slips
3 = partially in character / generic with some flavor
2 = weak persona; modern chatbot tone or wrong values dominate
1 = not in character
Punish modern anachronism and generic assistant phrasing.
Do not reward lexical overlap alone; judge character fidelity.
"""


@dataclass(frozen=True)
class JudgeResult:
    faithfulness: int
    persona: int
    faithfulness_notes: str = ""
    persona_notes: str = ""
    unsupported_claims: List[str] = field(default_factory=list)

    def as_report_dict(self) -> Dict[str, Any]:
        return {
            "faithfulness": self.faithfulness,
            "persona": self.persona,
            "faithfulness_notes": self.faithfulness_notes,
            "persona_notes": self.persona_notes,
            "unsupported_claims": list(self.unsupported_claims),
            "faithfulness_normalized": normalize_score_1_to_5(self.faithfulness),
            "persona_normalized": normalize_score_1_to_5(self.persona),
        }

    def as_telemetry_dict(self) -> Dict[str, Any]:
        return {
            "faithfulness": normalize_score_1_to_5(self.faithfulness),
            "persona": normalize_score_1_to_5(self.persona),
            "faithfulness_notes": self.faithfulness_notes,
            "persona_notes": self.persona_notes,
        }


def normalize_score_1_to_5(score: int | float) -> float:
    """Map a 1-5 rubric score onto `[0.0, 1.0]` for UI averages."""
    value = float(score)
    return round(max(0.0, min(1.0, (value - 1.0) / 4.0)), 4)


def _clamp_score(value: Any, *, default: int = 1) -> int:
    try:
        score = int(round(float(value)))
    except (TypeError, ValueError):
        return default
    return max(1, min(5, score))


def _extract_json_object(raw_text: str) -> Dict[str, Any]:
    text = (raw_text or "").strip()
    if not text:
        raise ValueError("Judge response was empty")

    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fenced:
        payload = json.loads(fenced.group(1))
        if isinstance(payload, dict):
            return payload

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        payload = json.loads(text[start : end + 1])
        if isinstance(payload, dict):
            return payload

    raise ValueError(f"Could not parse judge JSON from response: {text[:240]}")


def parse_judge_response(raw_text: str) -> JudgeResult:
    """Parse and validate a judge model response into a JudgeResult."""
    payload = _extract_json_object(raw_text)
    claims_raw = payload.get("unsupported_claims") or []
    if not isinstance(claims_raw, list):
        claims_raw = [str(claims_raw)]
    claims = [str(item).strip() for item in claims_raw if str(item).strip()]

    return JudgeResult(
        faithfulness=_clamp_score(payload.get("faithfulness"), default=1),
        persona=_clamp_score(payload.get("persona"), default=1),
        faithfulness_notes=str(payload.get("faithfulness_notes") or "").strip(),
        persona_notes=str(payload.get("persona_notes") or "").strip(),
        unsupported_claims=claims,
    )


def build_judge_user_prompt(
    *,
    agent_id: str,
    display_name: str,
    topic: str,
    system_prompt: str,
    retrieved_context: str,
    previous_response: str,
    answer: str,
) -> str:
    """Assemble the user message for the faithfulness + persona judge."""
    context_block = (retrieved_context or "").strip() or "(no retrieved context)"
    previous_block = (previous_response or "").strip() or "(none — first turn)"
    return (
        f"Agent ID: {agent_id}\n"
        f"Speaker: {display_name}\n"
        f"Topic: {topic.strip()}\n\n"
        f"Speaker system prompt:\n{system_prompt.strip()}\n\n"
        f"Retrieved speaker context:\n{context_block}\n\n"
        f"Previous debate turn:\n{previous_block}\n\n"
        f"Candidate answer:\n{answer.strip()}\n"
    )


async def judge_answer(
    *,
    complete_chat: Callable[..., Awaitable[str]],
    agent_id: str,
    display_name: str,
    topic: str,
    system_prompt: str,
    retrieved_context: str,
    previous_response: str,
    answer: str,
) -> JudgeResult:
    """Run the LLM judge and return a validated result."""
    user_prompt = build_judge_user_prompt(
        agent_id=agent_id,
        display_name=display_name,
        topic=topic,
        system_prompt=system_prompt,
        retrieved_context=retrieved_context,
        previous_response=previous_response,
        answer=answer,
    )
    raw = await complete_chat(
        [
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.0,
        max_tokens=450,
    )
    return parse_judge_response(raw)
