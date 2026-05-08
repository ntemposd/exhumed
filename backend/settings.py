from __future__ import annotations

import os
from pathlib import Path
from typing import List, Literal, Mapping, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, ValidationError


DEFAULT_CORS_ORIGINS = [
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


class LLMSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    api_key: str
    model_id: str = "llama-3.1-8b-instant"
    api_base_url: str = "https://api.groq.com/openai/v1"
    max_retries: int = 3
    request_throttle_seconds: float = 0.0


class RuntimeSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    startup_readiness_mode: Literal["off", "warn", "strict"] = "strict"


class BackendSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    base_dir: Path
    static_dir: Path
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

    raw_settings = {
        "base_dir": base_dir,
        "static_dir": base_dir / "static",
        "cors": {
            "allow_origins": _parse_cors_origins(env.get("CORS_ALLOW_ORIGINS")) or DEFAULT_CORS_ORIGINS,
            "allow_origin_regex": env.get(
                "CORS_ALLOW_ORIGIN_REGEX",
                r"https://.*\.vercel\.app|https?://(?:localhost|127\.0\.0\.1)(?::\d+)?",
            ),
        },
        "storage": {
            "redis_rest_url": env.get("UPSTASH_REDIS_REST_URL"),
            "redis_rest_token": env.get("UPSTASH_REDIS_REST_TOKEN"),
            "vector_rest_url": env.get("UPSTASH_VECTOR_REST_URL"),
            "vector_rest_token": env.get("UPSTASH_VECTOR_REST_TOKEN"),
            "agent_registry_cache_ttl_seconds": env.get("AGENT_REGISTRY_CACHE_TTL_SECONDS", "60.0"),
            "agent_config_cache_ttl_seconds": env.get("AGENT_CONFIG_CACHE_TTL_SECONDS", "300.0"),
        },
        "llm": {
            "api_key": env.get("LLM_API_KEY"),
            "model_id": env.get("LLM_MODEL_ID", "llama-3.1-8b-instant"),
            "api_base_url": env.get("LLM_API_BASE_URL", "https://api.groq.com/openai/v1"),
            "max_retries": env.get("LLM_429_MAX_RETRIES", "3"),
            "request_throttle_seconds": env.get("LLM_REQUEST_THROTTLE_SECONDS", "0.0"),
        },
        "runtime": {
            "startup_readiness_mode": env.get("BACKEND_STARTUP_READINESS_MODE", "strict").strip().lower(),
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