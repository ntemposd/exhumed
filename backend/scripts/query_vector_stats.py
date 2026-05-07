from __future__ import annotations

"""Query Upstash Vector and summarize matched chunks by agent and source."""

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv


SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
REPO_ROOT = BACKEND_DIR.parent

load_dotenv(REPO_ROOT / ".env")

UPSTASH_VECTOR_REST_URL = os.environ.get("UPSTASH_VECTOR_REST_URL")
UPSTASH_VECTOR_REST_TOKEN = os.environ.get("UPSTASH_VECTOR_REST_TOKEN")


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for query-scoped or full-index Vector summaries."""
    parser = argparse.ArgumentParser(description="Query Upstash Vector and summarize matching chunks")
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--query", help="Semantic query text")
    mode_group.add_argument("--all-agents", action="store_true", help="Scan the full Vector index and summarize every agent")
    parser.add_argument("--top-k", type=int, default=20, help="Maximum number of matching chunks to fetch")
    parser.add_argument("--scan-limit", type=int, default=100, help="Batch size when scanning the full Vector index")
    parser.add_argument("--namespace", default="", help="Optional Upstash Vector namespace")
    parser.add_argument("--agent-id", help="Optional agent_id filter")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a human-readable report")
    return parser.parse_args()


def create_vector_index():
    """Construct the Upstash Vector client from environment-backed credentials."""
    if not UPSTASH_VECTOR_REST_URL or not UPSTASH_VECTOR_REST_TOKEN:
        raise ValueError("Missing UPSTASH_VECTOR_REST_URL or UPSTASH_VECTOR_REST_TOKEN in environment")

    from upstash_vector import Index

    return Index(url=UPSTASH_VECTOR_REST_URL, token=UPSTASH_VECTOR_REST_TOKEN)


def build_agent_filter(agent_id: str | None) -> str | None:
    """Build a safe metadata filter for agent-scoped Vector queries."""
    if not agent_id:
        return None

    escaped_agent_id = agent_id.replace("\\", "\\\\").replace("'", "\\'")
    return f"agent_id = '{escaped_agent_id}'"


def query_vector_matches(
    *,
    query_text: str,
    top_k: int,
    namespace: str,
    agent_id: str | None,
) -> List[Dict[str, Any]]:
    """Use the same hosted-embedding query path as the live backend retrieval flow."""
    index = create_vector_index()
    query_kwargs: Dict[str, Any] = {
        "data": query_text,
        "top_k": max(1, top_k),
        "include_metadata": True,
        "include_data": True,
    }

    metadata_filter = build_agent_filter(agent_id)
    if metadata_filter:
        query_kwargs["filter"] = metadata_filter
    if namespace:
        query_kwargs["namespace"] = namespace

    results = index.query(**query_kwargs)
    matches: List[Dict[str, Any]] = []

    for item in results:
        matches.append(
            {
                "id": getattr(item, "id", None),
                "score": getattr(item, "score", None),
                "metadata": getattr(item, "metadata", None) or {},
                "data": getattr(item, "data", None) or "",
            }
        )

    return matches


def scan_all_vector_matches(*, namespace: str, agent_id: str | None, scan_limit: int) -> List[Dict[str, Any]]:
    """Walk the full Vector index when you need corpus-wide stats instead of query-local matches."""
    index = create_vector_index()
    matches: List[Dict[str, Any]] = []
    next_cursor = ""
    normalized_limit = max(1, scan_limit)

    while True:
        result = index.range(
            cursor=next_cursor,
            limit=normalized_limit,
            include_metadata=True,
            include_data=True,
            namespace=namespace or "",
        )

        for item in getattr(result, "vectors", []):
            metadata = getattr(item, "metadata", None) or {}
            if agent_id and str(metadata.get("agent_id") or "") != agent_id:
                continue

            matches.append(
                {
                    "id": getattr(item, "id", None),
                    "score": None,
                    "metadata": metadata,
                    "data": getattr(item, "data", None) or "",
                }
            )

        next_cursor = str(getattr(result, "next_cursor", "") or "")
        if not next_cursor:
            break

    return matches


def _build_char_stats(lengths: List[int]) -> Dict[str, float | int]:
    """Summarize chunk lengths into count, average, minimum, and maximum values."""
    if not lengths:
        return {
            "chunk_count": 0,
            "avg_chars": 0.0,
            "max_chars": 0,
            "min_chars": 0,
        }

    return {
        "chunk_count": len(lengths),
        "avg_chars": round(sum(lengths) / len(lengths), 1),
        "max_chars": max(lengths),
        "min_chars": min(lengths),
    }


def summarize_matches(matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Collapse raw chunk matches into per-agent and per-source character statistics."""
    grouped: Dict[str, Dict[str, Any]] = {}

    for match in matches:
        metadata = match.get("metadata") or {}
        agent_id = str(metadata.get("agent_id") or "unknown")
        speaker_name = str(metadata.get("speaker_name") or agent_id)
        source_title = str(metadata.get("source_title") or "Unknown Source")
        text = str(match.get("data") or "")
        char_count = len(text)

        agent_summary = grouped.setdefault(
            agent_id,
            {
                "agent_id": agent_id,
                "speaker_name": speaker_name,
                "sources": {},
                "chunk_lengths": [],
                "top_score": None,
            },
        )
        if agent_summary["top_score"] is None and isinstance(match.get("score"), (int, float)):
            agent_summary["top_score"] = float(match["score"])

        source_summary = agent_summary["sources"].setdefault(
            source_title,
            {
                "source_title": source_title,
                "chunk_lengths": [],
            },
        )

        agent_summary["chunk_lengths"].append(char_count)
        source_summary["chunk_lengths"].append(char_count)

    summaries: List[Dict[str, Any]] = []
    for agent_summary in grouped.values():
        source_summaries: List[Dict[str, Any]] = []
        for source_summary in agent_summary["sources"].values():
            source_summaries.append(
                {
                    "source_title": source_summary["source_title"],
                    **_build_char_stats(source_summary["chunk_lengths"]),
                }
            )

        source_summaries.sort(key=lambda item: item["source_title"])
        summaries.append(
            {
                "agent_id": agent_summary["agent_id"],
                "speaker_name": agent_summary["speaker_name"],
                "sources": [item["source_title"] for item in source_summaries],
                "source_stats": source_summaries,
                "top_score": agent_summary["top_score"],
                **_build_char_stats(agent_summary["chunk_lengths"]),
            }
        )

    summaries.sort(key=lambda item: (item["speaker_name"], item["agent_id"]))
    return summaries


def format_summary_report(report_label: str, summaries: List[Dict[str, Any]], total_matches: int) -> str:
    """Render the aggregated query stats in a terminal-friendly report."""
    lines = [
        report_label,
        f"Matched chunks: {total_matches}",
    ]

    if not summaries:
        lines.append("No matching chunks found.")
        return "\n".join(lines)

    for summary in summaries:
        top_score = summary.get("top_score")
        top_score_text = f"{top_score:.4f}" if isinstance(top_score, float) else "n/a"
        lines.extend(
            [
                "",
                f"Agent: {summary['speaker_name']} ({summary['agent_id']})",
                f"Sources: {', '.join(summary['sources'])}",
                f"Chunks: {summary['chunk_count']}",
                f"Avg chars: {summary['avg_chars']}",
                f"Max chars: {summary['max_chars']}",
                f"Min chars: {summary['min_chars']}",
                f"Top score: {top_score_text}",
                "Per-source stats:",
            ]
        )

        for source_summary in summary["source_stats"]:
            lines.append(
                "  - "
                f"{source_summary['source_title']}: "
                f"chunks={source_summary['chunk_count']}, "
                f"avg={source_summary['avg_chars']}, "
                f"max={source_summary['max_chars']}, "
                f"min={source_summary['min_chars']}"
            )

    return "\n".join(lines)


def main() -> None:
    """Execute the selected Vector stats mode and print the resulting report."""
    args = parse_args()
    if args.all_agents:
        matches = scan_all_vector_matches(
            namespace=args.namespace,
            agent_id=args.agent_id,
            scan_limit=args.scan_limit,
        )
        report_label = "Mode: full index scan"
    else:
        matches = query_vector_matches(
            query_text=str(args.query),
            top_k=args.top_k,
            namespace=args.namespace,
            agent_id=args.agent_id,
        )
        report_label = f"Query: {args.query}"

    summaries = summarize_matches(matches)

    if args.json:
        print(
            json.dumps(
                {
                    "query": args.query,
                    "mode": "all_agents" if args.all_agents else "query",
                    "matched_chunks": len(matches),
                    "results": summaries,
                },
                indent=2,
            )
        )
        return

    print(format_summary_report(report_label, summaries, len(matches)))


if __name__ == "__main__":
    main()