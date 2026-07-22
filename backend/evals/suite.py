from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence
from uuid import uuid4

try:
    from backend.evals.judge import JudgeResult, judge_answer
    from backend.utils.answer_evals import join_retrieval_context
except ImportError:  # pragma: no cover
    from evals.judge import JudgeResult, judge_answer
    from utils.answer_evals import join_retrieval_context

DEFAULT_FIXTURES_PATH = Path(__file__).resolve().parent / "fixtures" / "persona_faithfulness_v1.json"
DEFAULT_REPORTS_DIR = Path(__file__).resolve().parent / "reports"

MEAN_PERSONA_THRESHOLD = 3.5
MEAN_FAITHFULNESS_THRESHOLD = 3.5
MIN_PERSONA_FLOOR = 2


def load_fixtures(path: Path | None = None) -> Dict[str, Any]:
    fixtures_path = path or DEFAULT_FIXTURES_PATH
    payload = json.loads(fixtures_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise ValueError(f"Invalid fixtures file: {fixtures_path}")
    return payload


def filter_cases(
    cases: Sequence[Dict[str, Any]],
    *,
    agent_id: Optional[str] = None,
    case_ids: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    selected = list(cases)
    if agent_id:
        selected = [case for case in selected if case.get("agent_id") == agent_id]
    if case_ids:
        wanted = set(case_ids)
        selected = [case for case in selected if case.get("id") in wanted]
    return selected


def summarize_results(case_results: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    if not case_results:
        return {
            "case_count": 0,
            "mean_faithfulness": 0.0,
            "mean_persona": 0.0,
            "min_persona": 0.0,
            "passed": False,
            "failures": ["no_cases"],
        }

    faithfulness_scores = [float(item["judge"]["faithfulness"]) for item in case_results]
    persona_scores = [float(item["judge"]["persona"]) for item in case_results]
    mean_faithfulness = sum(faithfulness_scores) / len(faithfulness_scores)
    mean_persona = sum(persona_scores) / len(persona_scores)
    min_persona = min(persona_scores)

    failures: List[str] = []
    if mean_faithfulness < MEAN_FAITHFULNESS_THRESHOLD:
        failures.append(
            f"mean_faithfulness {mean_faithfulness:.2f} < {MEAN_FAITHFULNESS_THRESHOLD}"
        )
    if mean_persona < MEAN_PERSONA_THRESHOLD:
        failures.append(f"mean_persona {mean_persona:.2f} < {MEAN_PERSONA_THRESHOLD}")
    if min_persona <= MIN_PERSONA_FLOOR:
        failures.append(f"min_persona {min_persona:.0f} <= {MIN_PERSONA_FLOOR}")

    return {
        "case_count": len(case_results),
        "mean_faithfulness": round(mean_faithfulness, 3),
        "mean_persona": round(mean_persona, 3),
        "min_persona": float(min_persona),
        "passed": not failures,
        "failures": failures,
        "thresholds": {
            "mean_faithfulness": MEAN_FAITHFULNESS_THRESHOLD,
            "mean_persona": MEAN_PERSONA_THRESHOLD,
            "min_persona_floor": MIN_PERSONA_FLOOR,
        },
    }


async def evaluate_fixture_case(
    *,
    case: Dict[str, Any],
    fetch_agent_config: Callable[[str], Awaitable[Any]],
    get_agent_context_matches: Callable[[str, str], List[Dict[str, Any]]],
    build_context_prompt: Callable[..., str],
    call_llm_api: Callable[..., Awaitable[tuple[str, Any]]],
    complete_chat: Callable[..., Awaitable[str]],
    sanitize_generated_message: Callable[[str, str], str],
    system_prompt_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate one answer for a fixture case and LLM-judge it."""
    agent_id = str(case["agent_id"])
    topic = str(case["topic"])
    previous_response = str(case.get("previous_response") or "")

    agent_config = await fetch_agent_config(agent_id)
    if system_prompt_override is not None:
        agent_config = agent_config.model_copy(update={"system_prompt": system_prompt_override})

    context_messages: List[Dict[str, Any]] = []
    if previous_response.strip():
        context_messages.append(
            {
                "message": previous_response,
                "display_name": "Prior Speaker",
                "agent_id": "fixture_prior",
            }
        )

    matches = await asyncio.to_thread(get_agent_context_matches, topic, agent_id)
    retrieval_context_text = join_retrieval_context(matches)
    prompt = build_context_prompt(topic, context_messages, agent_config, matches)
    generated_message, _metrics = await call_llm_api(prompt, agent_config)
    answer = sanitize_generated_message(generated_message, agent_config.display_name)

    judge: JudgeResult = await judge_answer(
        complete_chat=complete_chat,
        agent_id=agent_id,
        display_name=agent_config.display_name,
        topic=topic,
        system_prompt=agent_config.system_prompt,
        retrieved_context=retrieval_context_text,
        previous_response=previous_response,
        answer=answer,
    )

    return {
        "id": case.get("id"),
        "agent_id": agent_id,
        "display_name": agent_config.display_name,
        "topic": topic,
        "previous_response": previous_response,
        "notes": case.get("notes"),
        "answer": answer,
        "retrieval_context_chars": len(retrieval_context_text),
        "match_count": len(matches),
        "judge": judge.as_report_dict(),
    }


async def run_eval_suite(
    *,
    fixtures: Dict[str, Any],
    fetch_agent_config: Callable[[str], Awaitable[Any]],
    get_agent_context_matches: Callable[[str, str], List[Dict[str, Any]]],
    build_context_prompt: Callable[..., str],
    call_llm_api: Callable[..., Awaitable[tuple[str, Any]]],
    complete_chat: Callable[..., Awaitable[str]],
    sanitize_generated_message: Callable[[str, str], str],
    agent_id: Optional[str] = None,
    case_ids: Optional[Sequence[str]] = None,
    system_prompt_override: Optional[str] = None,
) -> Dict[str, Any]:
    cases = filter_cases(fixtures.get("cases") or [], agent_id=agent_id, case_ids=case_ids)
    results: List[Dict[str, Any]] = []
    for case in cases:
        results.append(
            await evaluate_fixture_case(
                case=case,
                fetch_agent_config=fetch_agent_config,
                get_agent_context_matches=get_agent_context_matches,
                build_context_prompt=build_context_prompt,
                call_llm_api=call_llm_api,
                complete_chat=complete_chat,
                sanitize_generated_message=sanitize_generated_message,
                system_prompt_override=system_prompt_override,
            )
        )

    summary = summarize_results(results)
    return {
        "suite": fixtures.get("name") or "unnamed",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": str(uuid4()),
        "summary": summary,
        "cases": results,
    }


def write_report(report: Dict[str, Any], reports_dir: Path | None = None) -> Path:
    target_dir = reports_dir or DEFAULT_REPORTS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = target_dir / f"{stamp}_{report.get('suite', 'suite')}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
    return path


def latest_report_path(reports_dir: Path | None = None) -> Optional[Path]:
    target_dir = reports_dir or DEFAULT_REPORTS_DIR
    if not target_dir.exists():
        return None
    reports = sorted(target_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    return reports[0] if reports else None


def load_report(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def failing_cases_for_agent(
    report: Dict[str, Any],
    agent_id: str,
    *,
    below: float = MEAN_PERSONA_THRESHOLD,
) -> List[Dict[str, Any]]:
    failing: List[Dict[str, Any]] = []
    for case in report.get("cases") or []:
        if case.get("agent_id") != agent_id:
            continue
        judge = case.get("judge") or {}
        persona = float(judge.get("persona") or 0)
        faithfulness = float(judge.get("faithfulness") or 0)
        if persona < below or faithfulness < below:
            failing.append(case)
    return failing
