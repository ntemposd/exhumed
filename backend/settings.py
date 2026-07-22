from __future__ import annotations

import os
from pathlib import Path
from typing import List, Literal, Mapping, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, ValidationError


# Production URL is always included; localhost origins are added for local dev
# convenience. Override entirely via CORS_ALLOW_ORIGINS for strict production
# lock-down (comma-separated list).
# Browser requests from the frontend never reach Railway directly — they go
# through the Next.js /api/backend proxy on Vercel.  CORS only needs to cover
# local dev (where the browser does hit the backend directly) and the Vercel
# origins for cases where the proxy is not in use (e.g. direct API testing).
DEFAULT_CORS_ORIGINS = [
    "https://exhum.vercel.app",
    "https://exhumed.ntemposd.me",
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
]


def _parse_cors_origins(raw_value: Optional[str]) -> List[str]:
    if not raw_value:
        return []
    return [origin.strip().rstrip("/") for origin in raw_value.split(",") if origin.strip()]


def _resolve_base_dir(file_dir: Path) -> Path:
    repo_root_candidate = file_dir.parent
    if (repo_root_candidate / "backend" / "main.py").exists():
        return repo_root_candidate
    return file_dir


class AuthSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    # When set, every non-health request must include either:
    #   - Header:  X-API-Key: <api_key>
    #   - Header:  Authorization: Bearer <api_key>
    # Leave unset (or empty string) to disable authentication entirely.
    api_key: Optional[str] = None


class CorsSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    allow_origins: List[str]
    allow_origin_regex: str


class StorageSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    redis_rest_url: str
    redis_rest_token: str
    vector_rest_url: str
    vector_rest_token: str
    agent_registry_cache_ttl_seconds: float = 60.0
    agent_config_cache_ttl_seconds: float = 300.0
    # Maximum messages stored per session. Oldest messages are trimmed once this
    # limit is reached, preventing unbounded Redis list growth on Railway.
    session_max_messages: int = 200
    # Where to persist prompt captures for offline inspection.
    # "redis"  — appends to a capped Redis list (ephemeral-filesystem-safe).
    # "file"   — appends to a local JSONL file (dev only; breaks on Railway).
    # "off"    — disables prompt capture entirely.
    prompt_capture_backend: Literal["redis", "file", "off"] = "off"
    # Maximum prompt captures retained in Redis (only used when backend="redis").
    prompt_capture_max_entries: int = 500


class LLMSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    api_key: str
    model_id: str = "llama-3.1-8b-instant"
    api_base_url: str = "https://api.groq.com/openai/v1"
    max_retries: int = 3
    # Minimum spacing between provider calls (30 RPM on 8b-instant ≈ 2s/request).
    request_throttle_seconds: float = 2.0
    top_p: float = 0.95
    # Output cap for debate turns (agent config may be lower).
    debate_max_tokens: int = 384
    # Retrieval and prompt shaping to stay under TPM limits without dropping RAG entirely.
    retrieval_top_k: int = 4
    retrieval_weak_top_k_bonus: int = 1
    context_turn_limit: int = 4
    prompt_max_source_chunk_chars: int = 680
    prompt_max_context_turn_chars: int = 320


class RuntimeSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    startup_readiness_mode: Literal["off", "warn", "strict"] = "strict"
    # When true, each generated turn also runs the LLM-as-judge (faithfulness + persona).
    eval_online_judge: bool = False


class BackendSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    base_dir: Path
    static_dir: Path
    auth: AuthSettings
    cors: CorsSettings
    storage: StorageSettings
    llm: LLMSettings
    runtime: RuntimeSettings


def load_settings(
    *,
    environ: Optional[Mapping[str, str]] = None,
    file_dir: Optional[Path] = None,
) -> BackendSettings:
    resolved_file_dir = file_dir or Path(__file__).resolve().parent
    base_dir = _resolve_base_dir(resolved_file_dir)

    if environ is None:
        load_dotenv(base_dir / ".env")
        env: Mapping[str, str] = os.environ
    else:
        env = environ

    _raw_api_key = env.get("BACKEND_API_KEY", "").strip()

    raw_settings = {
        "base_dir": base_dir,
        "static_dir": base_dir / "static",
        "auth": {
            "api_key": _raw_api_key or None,
        },
        "cors": {
            "allow_origins": _parse_cors_origins(env.get("CORS_ALLOW_ORIGINS")) or DEFAULT_CORS_ORIGINS,
            "allow_origin_regex": env.get(
                "CORS_ALLOW_ORIGIN_REGEX",
                r"https://.*\.vercel\.app|https://exhumed\.ntemposd\.me|https?://(?:localhost|127\.0\.0\.1)(?::\d+)?",
            ),
        },
        "storage": {
            "redis_rest_url": env.get("UPSTASH_REDIS_REST_URL"),
            "redis_rest_token": env.get("UPSTASH_REDIS_REST_TOKEN"),
            "vector_rest_url": env.get("UPSTASH_VECTOR_REST_URL"),
            "vector_rest_token": env.get("UPSTASH_VECTOR_REST_TOKEN"),
            "agent_registry_cache_ttl_seconds": env.get("AGENT_REGISTRY_CACHE_TTL_SECONDS", "60.0"),
            "agent_config_cache_ttl_seconds": env.get("AGENT_CONFIG_CACHE_TTL_SECONDS", "300.0"),
            "session_max_messages": env.get("SESSION_MAX_MESSAGES", "200"),
            "prompt_capture_backend": env.get("PROMPT_CAPTURE_BACKEND", "off").strip().lower(),
            "prompt_capture_max_entries": env.get("PROMPT_CAPTURE_MAX_ENTRIES", "500"),
        },
        "llm": {
            "api_key": env.get("LLM_API_KEY"),
            "model_id": env.get("LLM_MODEL_ID", "llama-3.1-8b-instant"),
            "api_base_url": env.get("LLM_API_BASE_URL", "https://api.groq.com/openai/v1"),
            "max_retries": env.get("LLM_429_MAX_RETRIES", "3"),
            "request_throttle_seconds": env.get("LLM_REQUEST_THROTTLE_SECONDS", "2.0"),
            "top_p": env.get("LLM_TOP_P", "0.95"),
            "debate_max_tokens": env.get("LLM_DEBATE_MAX_TOKENS", "384"),
            "retrieval_top_k": env.get("LLM_RETRIEVAL_TOP_K", "4"),
            "retrieval_weak_top_k_bonus": env.get("LLM_RETRIEVAL_WEAK_TOP_K_BONUS", "1"),
            "context_turn_limit": env.get("LLM_CONTEXT_TURN_LIMIT", "4"),
            "prompt_max_source_chunk_chars": env.get("LLM_PROMPT_MAX_SOURCE_CHUNK_CHARS", "680"),
            "prompt_max_context_turn_chars": env.get("LLM_PROMPT_MAX_CONTEXT_TURN_CHARS", "320"),
        },
        "runtime": {
            "startup_readiness_mode": env.get("BACKEND_STARTUP_READINESS_MODE", "strict").strip().lower(),
            "eval_online_judge": env.get("EVAL_ONLINE_JUDGE", "off").strip().lower() in {"1", "true", "on", "yes"},
        },
    }

    try:
        settings = BackendSettings.model_validate(raw_settings)
    except ValidationError as exc:
        missing_fields = []
        invalid_fields = []
        for error in exc.errors():
            location = ".".join(str(part) for part in error.get("loc", ()))
            if error.get("type") == "string_type" and error.get("input") is None:
                missing_fields.append(location)
            else:
                invalid_fields.append(f"{location}: {error.get('msg')}")

        details = []
        if missing_fields:
            details.append("missing " + ", ".join(missing_fields))
        if invalid_fields:
            details.append("invalid " + "; ".join(invalid_fields))
        raise ValueError("Invalid backend settings: " + " | ".join(details)) from exc

    return settings