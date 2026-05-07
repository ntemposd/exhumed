import sys
import types
import unittest
from dataclasses import dataclass

try:
    from fastapi import HTTPException  # type: ignore
except ModuleNotFoundError:
    fastapi_module = types.ModuleType("fastapi")

    class HTTPException(Exception):
        def __init__(self, *, status_code, detail):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    fastapi_module.HTTPException = HTTPException
    sys.modules.setdefault("fastapi", fastapi_module)

from backend.services.agent_registry import AgentRegistryService


@dataclass
class FakeAgentConfig:
    agent_id: str
    display_name: str

    def model_copy(self, deep: bool = True):
        return FakeAgentConfig(agent_id=self.agent_id, display_name=self.display_name)

    def model_dump(self):
        return {"agent_id": self.agent_id, "display_name": self.display_name}


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.members = set()

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value):
        self.values[key] = value

    def sadd(self, key, value):
        if key == "agents:index":
            self.members.add(value)

    def smembers(self, key):
        if key == "agents:index":
            return list(self.members)
        return []


async def run_blocking_io(func, *args, **kwargs):
    return func(*args, **kwargs)


def parse_agent_payload(agent_id, payload):
    return FakeAgentConfig(agent_id=agent_id, display_name=payload)


class AgentRegistryServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.redis = FakeRedis()
        self.service = AgentRegistryService(
            redis_client=self.redis,
            decode_value=str,
            parse_agent_payload=parse_agent_payload,
            run_blocking_io=run_blocking_io,
            registry_ttl_seconds=60.0,
            config_ttl_seconds=60.0,
        )

    async def test_fetch_agent_config_uses_cache_after_first_load(self):
        self.redis.set("agent:agt_001", "Socrates")

        first = await self.service.fetch_agent_config("agt_001")
        self.redis.set("agent:agt_001", "Changed")
        second = await self.service.fetch_agent_config("agt_001")

        self.assertEqual(first.display_name, "Socrates")
        self.assertEqual(second.display_name, "Socrates")
        self.assertIsNot(first, second)

    async def test_register_agent_invalidates_registry_cache(self):
        await self.service.register_agent("agt_002", {"display_name": "Steve Jobs"})

        agents = await self.service.list_agents()

        self.assertEqual(agents, [{"agent_id": "agt_002", "display_name": '{"display_name": "Steve Jobs"}'}])

    async def test_fetch_agent_config_raises_404_when_missing(self):
        with self.assertRaises(Exception) as context:
            await self.service.fetch_agent_config("missing")

        self.assertEqual(getattr(context.exception, "status_code", None), 404)