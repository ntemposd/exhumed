from __future__ import annotations

import copy
import json
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

from fastapi import HTTPException


class AgentRegistryService:
    """Owns agent registry persistence plus short-lived in-memory config caches."""

    def __init__(
        self,
        *,
        redis_client: Any,
        decode_value: Callable[[Any], str],
        parse_agent_payload: Callable[[str, str], Any],
        run_blocking_io: Callable[..., Awaitable[Any]],
        registry_ttl_seconds: float,
        config_ttl_seconds: float,
    ) -> None:
        self.redis = redis_client
        self.decode_value = decode_value
        self.parse_agent_payload = parse_agent_payload
        self.run_blocking_io = run_blocking_io
        self.registry_ttl_seconds = registry_ttl_seconds
        self.config_ttl_seconds = config_ttl_seconds
        self._agent_registry_cache: Dict[str, Any] = {
            "expires_at": 0.0,
            "agents": [],
        }
        self._agent_config_cache: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def _clone_model(value: Any) -> Any:
        if hasattr(value, "model_copy") and callable(getattr(value, "model_copy")):
            return value.model_copy(deep=True)
        return copy.deepcopy(value)

    def invalidate_agent_registry_cache(self) -> None:
        """Drop the cached agent listing so the next read hits Redis."""
        self._agent_registry_cache["expires_at"] = 0.0
        self._agent_registry_cache["agents"] = []

    def invalidate_agent_config_cache(self, agent_id: Optional[str] = None) -> None:
        """Drop one cached agent config or all cached configs."""
        if agent_id is None:
            self._agent_config_cache.clear()
            return
        self._agent_config_cache.pop(agent_id, None)

    def get_cached_agent_registry(self) -> Optional[List[Dict[str, Any]]]:
        """Return a defensive copy of the cached agent listing when it is still fresh."""
        if time.monotonic() >= float(self._agent_registry_cache["expires_at"]):
            return None
        cached_agents = self._agent_registry_cache.get("agents", [])
        return [dict(agent) for agent in cached_agents]

    def set_cached_agent_registry(self, agents: List[Dict[str, Any]]) -> None:
        """Store a normalized agent listing in the in-memory cache."""
        self._agent_registry_cache["agents"] = [dict(agent) for agent in agents]
        self._agent_registry_cache["expires_at"] = time.monotonic() + self.registry_ttl_seconds

    def get_cached_agent_config(self, agent_id: str) -> Optional[Any]:
        """Return a cloned cached agent config when the entry is still valid."""
        cached_item = self._agent_config_cache.get(agent_id)
        if not cached_item:
            return None
        if time.monotonic() >= float(cached_item["expires_at"]):
            self._agent_config_cache.pop(agent_id, None)
            return None
        return self._clone_model(cached_item["agent_config"])

    def set_cached_agent_config(self, agent_config: Any) -> None:
        """Cache a cloned copy of an agent config for subsequent requests."""
        self._agent_config_cache[getattr(agent_config, "agent_id")] = {
            "expires_at": time.monotonic() + self.config_ttl_seconds,
            "agent_config": self._clone_model(agent_config),
        }

    async def fetch_agent_config(self, agent_id: str) -> Any:
        """Load an agent config from cache or Redis and normalize missing-agent errors."""
        try:
            cached_config = self.get_cached_agent_config(agent_id)
            if cached_config is not None:
                return cached_config

            payload = await self.run_blocking_io(self.redis.get, f"agent:{agent_id}")
            if not payload:
                raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found in registry")

            agent_config = self.parse_agent_payload(agent_id, self.decode_value(payload))
            self.set_cached_agent_config(agent_config)
            return agent_config
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Error fetching agent configuration") from exc

    async def register_agent(self, agent_id: str, payload: Dict[str, Any]) -> None:
        """Persist an agent definition and invalidate any stale registry caches."""
        serialized_payload = json.dumps(payload)

        def _register_agent() -> None:
            self.redis.set(f"agent:{agent_id}", serialized_payload)
            self.redis.sadd("agents:index", agent_id)

        try:
            await self.run_blocking_io(_register_agent)
            self.invalidate_agent_registry_cache()
            self.invalidate_agent_config_cache(agent_id)
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Error registering agent") from exc

    async def list_agents(self) -> List[Dict[str, Any]]:
        """Return the current agent registry, preferring the cache when it is valid."""
        try:
            cached_agents = self.get_cached_agent_registry()
            if cached_agents is not None:
                return cached_agents

            def _load_agents() -> List[Dict[str, Any]]:
                ids = self.redis.smembers("agents:index") or []
                agent_ids = sorted(self.decode_value(item) for item in ids)
                agents: List[Dict[str, Any]] = []

                for agent_id in agent_ids:
                    payload = self.redis.get(f"agent:{agent_id}")
                    if not payload:
                        continue
                    agent = self.parse_agent_payload(agent_id, self.decode_value(payload))
                    if hasattr(agent, "model_dump") and callable(getattr(agent, "model_dump")):
                        agents.append(agent.model_dump())
                    else:
                        agents.append(copy.deepcopy(agent))

                return agents

            agents = await self.run_blocking_io(_load_agents)
            self.set_cached_agent_registry(agents)
            return agents
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Error listing agents") from exc