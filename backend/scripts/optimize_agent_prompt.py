from __future__ import annotations

"""Propose and optionally apply a system_prompt revision from failing eval cases.

Usage:
  .\\.venv\\Scripts\\python.exe -m backend.scripts.optimize_agent_prompt --agent-id agt_001
  .\\.venv\\Scripts\\python.exe -m backend.scripts.optimize_agent_prompt --agent-id agt_001 --apply
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from backend.evals.runtime import build_eval_services
    from backend.evals.suite import (
        DEFAULT_FIXTURES_PATH,
        failing_cases_for_agent,
        latest_report_path,
        load_fixtures,
        load_report,
        run_eval_suite,
        write_report,
    )
except ModuleNotFoundError:  # pragma: no cover
    from evals.runtime import build_eval_services
    from evals.suite import (
        DEFAULT_FIXTURES_PATH,
        failing_cases_for_agent,
        latest_report_path,
        load_fixtures,
        load_report,
        run_eval_suite,
        write_report,
    )

OPTIMIZER_SYSTEM_PROMPT = """You revise system prompts for historical debate personas.
Return ONLY the revised system prompt text (no markdown fences, no commentary).
Constraints:
- Keep the same historical identity and core values
- Strengthen anti-drift instructions so the model stays in character
- Prefer grounding answers in the speaker's retrieved source material
- Do not invent biographical facts
- Keep the prompt concise and operational
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Optimize an agent system_prompt from eval failures")
    parser.add_argument("--agent-id", required=True, help="Agent id to optimize, e.g. agt_001")
    parser.add_argument("--report", type=Path, help="Path to an eval report JSON (defaults to latest)")
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES_PATH, help="Fixtures used for re-eval")
    parser.add_argument(
        "--below",
        type=float,
        default=3.5,
        help="Treat cases with persona or faithfulness below this score as optimization inputs (default: 3.5)",
    )
    parser.add_argument("--apply", action="store_true", help="Write the revised prompt to the agent registry if re-eval improves")
    return parser.parse_args()


def _build_optimizer_user_prompt(
    *,
    agent_id: str,
    display_name: str,
    current_prompt: str,
    failing_cases: List[Dict[str, Any]],
) -> str:
    case_blocks: List[str] = []
    for case in failing_cases[:6]:
        judge = case.get("judge") or {}
        case_blocks.append(
            "\n".join(
                [
                    f"Case: {case.get('id')}",
                    f"Topic: {case.get('topic')}",
                    f"Faithfulness: {judge.get('faithfulness')} — {judge.get('faithfulness_notes')}",
                    f"Persona: {judge.get('persona')} — {judge.get('persona_notes')}",
                    f"Unsupported claims: {judge.get('unsupported_claims')}",
                    f"Answer excerpt: {str(case.get('answer') or '')[:700]}",
                ]
            )
        )
    return (
        f"Agent ID: {agent_id}\n"
        f"Speaker: {display_name}\n\n"
        f"Current system prompt:\n{current_prompt.strip()}\n\n"
        f"Failing judged cases:\n\n"
        + "\n\n---\n\n".join(case_blocks)
        + "\n\nWrite an improved system prompt for this speaker."
    )


def _mean(report: Dict[str, Any], key: str) -> float:
    return float((report.get("summary") or {}).get(key) or 0.0)


async def _async_main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    args = parse_args()

    report_path = args.report or latest_report_path()
    if report_path is None or not report_path.exists():
        print("No eval report found. Run: python -m backend.scripts.run_eval_suite")
        return 2

    report = load_report(report_path)
    failing = failing_cases_for_agent(report, args.agent_id, below=float(args.below))
    if not failing:
        print(f"No cases below {args.below} for {args.agent_id} in {report_path}")
        return 0

    services = build_eval_services()
    agents = services["agent_registry_service"]
    session = services["session_service"]
    llm = services["llm_service"]

    agent_config = await agents.fetch_agent_config(args.agent_id)
    current_prompt = str(agent_config.system_prompt)
    optimizer_user = _build_optimizer_user_prompt(
        agent_id=args.agent_id,
        display_name=agent_config.display_name,
        current_prompt=current_prompt,
        failing_cases=failing,
    )
    proposed_prompt = (
        await llm.complete_chat(
            [
                {"role": "system", "content": OPTIMIZER_SYSTEM_PROMPT},
                {"role": "user", "content": optimizer_user},
            ],
            temperature=0.2,
            max_tokens=700,
        )
    ).strip()
    if proposed_prompt.startswith("```"):
        proposed_prompt = proposed_prompt.strip("`")
        if proposed_prompt.lower().startswith("text"):
            proposed_prompt = proposed_prompt[4:].lstrip()

    fixtures = load_fixtures(args.fixtures)
    before = await run_eval_suite(
        fixtures=fixtures,
        fetch_agent_config=agents.fetch_agent_config,
        get_agent_context_matches=session.get_agent_context_matches,
        build_context_prompt=session.build_context_prompt,
        call_llm_api=llm.call_llm_api,
        complete_chat=llm.complete_chat,
        sanitize_generated_message=session.sanitize_generated_message,
        agent_id=args.agent_id,
        system_prompt_override=current_prompt,
    )
    after = await run_eval_suite(
        fixtures=fixtures,
        fetch_agent_config=agents.fetch_agent_config,
        get_agent_context_matches=session.get_agent_context_matches,
        build_context_prompt=session.build_context_prompt,
        call_llm_api=llm.call_llm_api,
        complete_chat=llm.complete_chat,
        sanitize_generated_message=session.sanitize_generated_message,
        agent_id=args.agent_id,
        system_prompt_override=proposed_prompt,
    )

    before_persona = _mean(before, "mean_persona")
    after_persona = _mean(after, "mean_persona")
    before_faith = _mean(before, "mean_faithfulness")
    after_faith = _mean(after, "mean_faithfulness")
    improved = (after_persona + after_faith) > (before_persona + before_faith)

    artifact = {
        "agent_id": args.agent_id,
        "source_report": str(report_path),
        "failing_case_ids": [case.get("id") for case in failing],
        "current_prompt": current_prompt,
        "proposed_prompt": proposed_prompt,
        "before_summary": before.get("summary"),
        "after_summary": after.get("summary"),
        "improved": improved,
        "applied": False,
    }

    if args.apply and improved:
        payload = {
            "display_name": agent_config.display_name,
            "system_prompt": proposed_prompt,
            "temperature": float(agent_config.temperature),
            "max_tokens": int(agent_config.max_tokens),
        }
        await agents.register_agent(args.agent_id, payload)
        artifact["applied"] = True
        print(f"Applied revised system_prompt for {args.agent_id}")
    elif args.apply and not improved:
        print("Re-eval did not improve combined means; prompt not applied.")

    out_path = report_path.with_name(report_path.stem + f"-optimize-{args.agent_id}.json")
    out_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=True), encoding="utf-8")
    write_report(after)

    print(f"Source report: {report_path}")
    print(f"Optimize artifact: {out_path}")
    print(f"before persona={before_persona:.3f} faithfulness={before_faith:.3f}")
    print(f"after  persona={after_persona:.3f} faithfulness={after_faith:.3f}")
    print(f"improved={improved} applied={artifact['applied']}")
    return 0 if improved else 1


def main() -> None:
    raise SystemExit(asyncio.run(_async_main()))


if __name__ == "__main__":
    main()
