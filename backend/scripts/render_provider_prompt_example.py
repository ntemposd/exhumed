from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from uuid import UUID

from dotenv import load_dotenv


SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
REPO_ROOT = BACKEND_DIR.parent
DEFAULT_CAPTURE_FILE = BACKEND_DIR / "logs" / "provider_prompt_captures.jsonl"

for candidate in (REPO_ROOT, BACKEND_DIR):
    candidate_text = str(candidate)
    if candidate_text not in sys.path:
        sys.path.insert(0, candidate_text)

try:
    from backend.settings import load_settings
except ModuleNotFoundError:
    from settings import load_settings

load_dotenv(REPO_ROOT / ".env")


@dataclass(frozen=True)
class PromptExample:
    source: str
    debate_date: str
    session_id: Optional[str]
    agent_id: str
    display_name: str
    topic: str
    mode: str
    provider_url: str
    model_id: str
    temperature: float
    max_tokens: int
    context_turns: int
    vector_matches: int
    context_messages: List[Dict[str, Any]]
    vector_context: List[Dict[str, Any]]
    prompt: str
    payloads: Dict[str, Dict[str, Any]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render the real debate-turn prompt and provider payload as Markdown",
    )
    parser.add_argument("--agent-id", help="Agent id to load from the registry or filter local captures")
    parser.add_argument("--topic", help="Topic text used for retrieval and prompt framing or filter local captures")
    parser.add_argument("--session-id", help="Optional session id used to load recent saved turns")
    parser.add_argument(
        "--latest-capture",
        action="store_true",
        help="Render the latest locally captured real provider request instead of reconstructing one from Redis and Vector",
    )
    parser.add_argument(
        "--capture-file",
        default=str(DEFAULT_CAPTURE_FILE),
        help="Path to the local JSONL prompt capture file",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        help="Optional runtime temperature override; defaults to the agent config value",
    )
    parser.add_argument(
        "--context-limit",
        type=int,
        default=5,
        help="Maximum number of recent turns to include from session history",
    )
    parser.add_argument(
        "--mode",
        choices=("stream", "non-stream", "compare"),
        default="stream",
        help="Which provider payload shape to render",
    )
    parser.add_argument(
        "--output",
        help="Optional path to write the Markdown report to disk; stdout is always used when omitted",
    )
    args = parser.parse_args()
    if not args.latest_capture and (not args.agent_id or not args.topic):
        parser.error("--agent-id and --topic are required unless --latest-capture is used")
    return args


def decode_redis_value(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def parse_agent_payload(agent_id: str, payload: str) -> Dict[str, Any]:
    raw = json.loads(payload)
    return SimpleNamespace(
        agent_id=agent_id,
        display_name=raw["display_name"],
        system_prompt=raw["system_prompt"],
        temperature=float(raw.get("temperature", 0.7)),
        max_tokens=int(raw.get("max_tokens", 512)),
    )


async def run_blocking_io(func: Any, *args: Any, **kwargs: Any) -> Any:
    return await asyncio.to_thread(func, *args, **kwargs)


def build_provider_payload(
    *,
    provider_url: str,
    model_id: str,
    prompt: str,
    max_tokens: int,
    temperature: float,
    stream: bool,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "request_url": provider_url.rstrip("/") + "/chat/completions",
        "body": {
            "model": model_id,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": 0.95,
            "stream": stream,
        },
    }
    if stream:
        payload["body"]["stream_options"] = {"include_usage": True}
    return payload


def _slugify_topic(topic: str, *, fallback: str = "untitled-debate") -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", topic.casefold()).strip("-")
    return normalized[:80] or fallback


def resolve_output_path(args: argparse.Namespace, example: PromptExample) -> Path:
    if args.output:
        return Path(args.output)

    source_suffix = "capture" if example.source == "capture" else "reconstructed"
    file_name = f"{example.debate_date}_{_slugify_topic(example.topic)}_{source_suffix}.md"
    return BACKEND_DIR / "logs" / file_name


def render_markdown(example: PromptExample) -> str:
    mode_label = {
        "stream": "streaming",
        "non-stream": "non-streaming",
        "compare": "compare",
    }.get(example.mode, example.mode)
    lines = [
        "# Provider Prompt Example",
        "",
        "This report is generated from a locally captured real provider request." if example.source == "capture" else "This report is generated from the live backend prompt builder.",
        "The provider request is JSON over HTTP. The prompt itself is raw text placed in `body.messages[0].content`.",
        "",
        "## Inputs",
        "",
        f"- Source: {example.source}",
        f"- Debate date: {example.debate_date}",
        f"- Agent: {example.display_name} ({example.agent_id})",
        f"- Topic: {example.topic}",
        f"- Session ID: {example.session_id or 'none; no recent discussion context loaded'}",
        f"- Context turns loaded: {example.context_turns}",
        f"- Vector matches loaded: {example.vector_matches}",
        f"- Provider mode: {mode_label}",
        f"- Provider URL: {example.provider_url}",
        f"- Model: {example.model_id}",
        f"- Temperature: {example.temperature}",
        f"- Max tokens: {example.max_tokens}",
        "",
        "## Retrieved Vector Context",
        "",
    ]

    if example.vector_context:
        for index, match in enumerate(example.vector_context, start=1):
            source = str(match.get("source_title") or "Unknown Source")
            score = match.get("score")
            chunk_id = str(match.get("id") or "")
            chunk_text = str(match.get("data") or "")
            lines.extend(
                [
                    f"### Match {index}",
                    "",
                    f"- Source: {source}",
                    f"- Score: {score if score is not None else '--'}",
                    f"- Chunk ID: {chunk_id or '--'}",
                    "",
                    "````text",
                    chunk_text,
                    "````",
                    "",
                ]
            )
    else:
        lines.extend([
            "No vector matches were returned for this topic and agent.",
            "",
        ])

    lines.extend([
        "## Raw Stored Context Messages",
        "",
    ])

    if example.context_messages:
        lines.extend([
            "````json",
            json.dumps(example.context_messages, indent=2, ensure_ascii=True),
            "````",
            "",
        ])
    else:
        lines.extend([
            "No prior saved turns were loaded for this example.",
            "",
        ])

    lines.extend([
        "## Assembled Prompt",
        "",
        "````text",
        example.prompt,
        "````",
        "",
        "## Provider JSON",
        "",
    ])

    if example.mode == "compare":
        for label in ("stream", "non-stream"):
            payload = example.payloads.get(label)
            if not payload:
                continue
            lines.extend([
                f"### {label.title()} Payload",
                "",
                "````json",
                json.dumps(payload, indent=2, ensure_ascii=True),
                "````",
                "",
            ])
    else:
        payload = example.payloads[example.mode]
        lines.extend([
            "````json",
            json.dumps(payload, indent=2, ensure_ascii=True),
            "````",
            "",
        ])

    lines.extend([
        "## What The Provider Sees",
        "",
        "- Transport: JSON request body over HTTP.",
        "- Prompt format: one raw text string.",
        "- Exact location of that string: `body.messages[0].content`.",
    ])
    return "\n".join(lines) + "\n"


def build_payloads_for_mode(
    *,
    provider_url: str,
    model_id: str,
    prompt: str,
    max_tokens: int,
    temperature: float,
    mode: str,
    actual_provider_request: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    if mode == "compare":
        payloads = {
            "stream": build_provider_payload(
                provider_url=provider_url,
                model_id=model_id,
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=True,
            ),
            "non-stream": build_provider_payload(
                provider_url=provider_url,
                model_id=model_id,
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=False,
            ),
        }
        if actual_provider_request is not None:
            actual_mode = "stream" if actual_provider_request.get("body", {}).get("stream") else "non-stream"
            payloads[actual_mode] = actual_provider_request
        return payloads

    if actual_provider_request is not None and bool(actual_provider_request.get("body", {}).get("stream")) == (mode == "stream"):
        return {mode: actual_provider_request}

    return {
        mode: build_provider_payload(
            provider_url=provider_url,
            model_id=model_id,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=mode == "stream",
        )
    }


def load_latest_captured_example(args: argparse.Namespace) -> PromptExample:
    capture_path = Path(args.capture_file)
    if not capture_path.exists():
        raise FileNotFoundError(f"No local capture file found at {capture_path}")

    latest_record: Optional[Dict[str, Any]] = None
    for raw_line in reversed(capture_path.read_text(encoding="utf-8").splitlines()):
        if not raw_line.strip():
            continue
        try:
            record = json.loads(raw_line)
        except json.JSONDecodeError:
            continue

        if args.agent_id and str(record.get("agent_id") or "") != args.agent_id:
            continue
        if args.session_id and str(record.get("session_id") or "") != args.session_id:
            continue
        if args.topic and args.topic.casefold() not in str(record.get("topic") or "").casefold():
            continue

        latest_record = record
        break

    if latest_record is None:
        raise ValueError("No local prompt capture matched the provided filters")

    prompt = str(latest_record.get("prompt") or "")
    provider_request = latest_record.get("provider_request") or {}
    provider_url = str(latest_record.get("provider_url") or provider_request.get("request_url", "")).rsplit("/chat/completions", 1)[0]
    model_id = str(latest_record.get("model_id") or provider_request.get("body", {}).get("model") or "")
    temperature = float(latest_record.get("temperature") or provider_request.get("body", {}).get("temperature") or 0.0)
    max_tokens = int(latest_record.get("max_tokens") or provider_request.get("body", {}).get("max_tokens") or 0)

    return PromptExample(
        source="capture",
        debate_date=str(latest_record.get("captured_at") or "")[:10] or datetime.now(timezone.utc).date().isoformat(),
        session_id=str(latest_record.get("session_id") or "") or None,
        agent_id=str(latest_record.get("agent_id") or ""),
        display_name=str(latest_record.get("display_name") or latest_record.get("agent_id") or ""),
        topic=str(latest_record.get("topic") or ""),
        mode=args.mode,
        provider_url=provider_url,
        model_id=model_id,
        temperature=temperature,
        max_tokens=max_tokens,
        context_turns=int(latest_record.get("context_turns") or len(latest_record.get("context_messages") or [])),
        vector_matches=int(latest_record.get("vector_matches") or len(latest_record.get("vector_context") or [])),
        context_messages=list(latest_record.get("context_messages") or []),
        vector_context=list(latest_record.get("vector_context") or []),
        prompt=prompt,
        payloads=build_payloads_for_mode(
            provider_url=provider_url,
            model_id=model_id,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            mode=args.mode,
            actual_provider_request=provider_request if isinstance(provider_request, dict) else None,
        ),
    )


async def build_prompt_example(args: argparse.Namespace) -> PromptExample:
    settings = load_settings(file_dir=BACKEND_DIR)

    try:
        from upstash_redis import Redis
        from upstash_vector import Index

        from backend.services.agent_registry import AgentRegistryService
        from backend.services.database import DatabaseService, SentenceTransformerEmbeddingProvider
        from backend.services.session_service import SessionService
    except ModuleNotFoundError:
        from upstash_redis import Redis
        from upstash_vector import Index

        from services.agent_registry import AgentRegistryService
        from services.database import DatabaseService, SentenceTransformerEmbeddingProvider
        from services.session_service import SessionService

    logger = logging.getLogger(__name__)
    redis_client = Redis(url=settings.storage.redis_rest_url, token=settings.storage.redis_rest_token)
    vector_client = Index(url=settings.storage.vector_rest_url, token=settings.storage.vector_rest_token)

    database_service = DatabaseService(
        redis_client=redis_client,
        vector_index=vector_client,
        embedding_provider=SentenceTransformerEmbeddingProvider(),
    )
    agent_registry = AgentRegistryService(
        redis_client=redis_client,
        decode_value=decode_redis_value,
        parse_agent_payload=parse_agent_payload,
        run_blocking_io=run_blocking_io,
        registry_ttl_seconds=settings.storage.agent_registry_cache_ttl_seconds,
        config_ttl_seconds=settings.storage.agent_config_cache_ttl_seconds,
    )
    session_service = SessionService(
        redis_client=redis_client,
        database_service=database_service,
        run_blocking_io=run_blocking_io,
        decode_value=decode_redis_value,
        export_session_pdf=lambda *args, **kwargs: "",
        logger=logger,
    )

    session_id: Optional[UUID] = UUID(args.session_id) if args.session_id else None
    agent_config = await agent_registry.fetch_agent_config(args.agent_id)
    context_messages: List[Dict[str, Any]] = []
    if session_id is not None:
        context_messages = await session_service.fetch_context_messages(
            session_id,
            max(0, args.context_limit),
            args.topic,
        )
    agent_context_matches = session_service.get_agent_context_matches(args.topic, args.agent_id)
    prompt = session_service.build_context_prompt(
        args.topic,
        context_messages,
        agent_config,
        agent_context_matches,
    )

    effective_temperature = (
        float(args.temperature)
        if isinstance(args.temperature, (int, float))
        else float(agent_config["temperature"] if isinstance(agent_config, dict) else agent_config.temperature)
    )
    max_tokens = int(agent_config["max_tokens"] if isinstance(agent_config, dict) else agent_config.max_tokens)
    display_name = str(agent_config["display_name"] if isinstance(agent_config, dict) else agent_config.display_name)
    payloads = build_payloads_for_mode(
        provider_url=settings.llm.api_base_url,
        model_id=settings.llm.model_id,
        prompt=prompt,
        max_tokens=max_tokens,
        temperature=effective_temperature,
        mode=args.mode,
    )

    vector_context = [
        {
            "id": match.get("id"),
            "score": match.get("score"),
            "source_title": (match.get("metadata") or {}).get("source_title"),
            "data": match.get("data") or "",
        }
        for match in agent_context_matches
    ]

    return PromptExample(
        source="reconstructed",
        debate_date=(
            str(context_messages[-1].get("created_at") or "")[:10]
            if context_messages and context_messages[-1].get("created_at")
            else datetime.now(timezone.utc).date().isoformat()
        ),
        session_id=str(session_id) if session_id is not None else None,
        agent_id=args.agent_id,
        display_name=display_name,
        topic=args.topic,
        mode=args.mode,
        provider_url=settings.llm.api_base_url,
        model_id=settings.llm.model_id,
        temperature=effective_temperature,
        max_tokens=max_tokens,
        context_turns=len(context_messages),
        vector_matches=len(agent_context_matches),
        context_messages=context_messages,
        vector_context=vector_context,
        prompt=prompt,
        payloads=payloads,
    )


async def async_main() -> int:
    args = parse_args()
    example = load_latest_captured_example(args) if args.latest_capture else await build_prompt_example(args)
    markdown = render_markdown(example)

    output_path = resolve_output_path(args, example)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")

    print(markdown, end="")
    print(f"\nSaved report to: {output_path}")
    return 0


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())