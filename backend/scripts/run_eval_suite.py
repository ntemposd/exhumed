from __future__ import annotations

"""Run the offline faithfulness + persona LLM-as-judge suite.

Usage:
  .\\.venv\\Scripts\\python.exe -m backend.scripts.run_eval_suite
  .\\.venv\\Scripts\\python.exe -m backend.scripts.run_eval_suite --agent-id agt_001
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from backend.evals.runtime import build_eval_services
    from backend.evals.suite import DEFAULT_FIXTURES_PATH, load_fixtures, run_eval_suite, write_report
except ModuleNotFoundError:  # pragma: no cover
    from evals.runtime import build_eval_services
    from evals.suite import DEFAULT_FIXTURES_PATH, load_fixtures, run_eval_suite, write_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run offline persona/faithfulness eval suite")
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES_PATH, help="Path to fixtures JSON")
    parser.add_argument("--agent-id", help="Only evaluate fixtures for this agent_id")
    parser.add_argument("--case-id", action="append", dest="case_ids", help="Limit to one or more fixture ids")
    return parser.parse_args()


async def _async_main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    args = parse_args()
    fixtures = load_fixtures(args.fixtures)
    services = build_eval_services()
    session = services["session_service"]
    llm = services["llm_service"]
    agents = services["agent_registry_service"]

    report = await run_eval_suite(
        fixtures=fixtures,
        fetch_agent_config=agents.fetch_agent_config,
        get_agent_context_matches=session.get_agent_context_matches,
        build_context_prompt=session.build_context_prompt,
        call_llm_api=llm.call_llm_api,
        complete_chat=llm.complete_chat,
        sanitize_generated_message=session.sanitize_generated_message,
        agent_id=args.agent_id,
        case_ids=args.case_ids,
    )
    path = write_report(report)
    summary = report["summary"]
    print(f"Wrote report: {path}")
    print(
        "mean_faithfulness={mean_faithfulness} mean_persona={mean_persona} "
        "min_persona={min_persona} passed={passed}".format(**summary)
    )
    if summary.get("failures"):
        print("failures:")
        for item in summary["failures"]:
            print(f"  - {item}")
    return 0 if summary.get("passed") else 1


def main() -> None:
    raise SystemExit(asyncio.run(_async_main()))


if __name__ == "__main__":
    main()
