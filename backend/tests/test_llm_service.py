import unittest
from types import SimpleNamespace

from backend.services.llm_service import LLMService


class LLMServicePromptRoleTests(unittest.IsolatedAsyncioTestCase):
    async def test_call_llm_api_sends_system_and_user_messages(self):
        service = LLMService(
            api_base_url="https://api.example.com/v1",
            api_key="test-key",
            model_id="demo-model",
            max_retries=0,
            throttle_seconds=0.0,
            execution_metrics_builder=lambda **kwargs: SimpleNamespace(**kwargs),
            extract_execution_metrics=lambda *args, **kwargs: SimpleNamespace(generation_duration_ms=1),
            build_stream_execution_metrics=lambda **kwargs: SimpleNamespace(**kwargs),
            logger=SimpleNamespace(error=lambda *args, **kwargs: None),
        )

        captured = {}

        def fake_build_provider_request(*, messages, agent_config, temperature_override=None, stream):
            captured["messages"] = messages
            return {
                "request_url": "https://api.example.com/v1/chat/completions",
                "body": {"messages": messages, "stream": stream},
            }

        class FakeResponse:
            headers = {}

            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": "Grounded answer."}}]}

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, url, json, headers):
                captured["request_url"] = url
                captured["payload"] = json
                return FakeResponse()

        async def fake_wait_for_provider_slot():
            return None

        service.build_provider_request = fake_build_provider_request
        service._wait_for_provider_slot = fake_wait_for_provider_slot
        service._http_client_context = lambda timeout: FakeClient()

        agent_config = SimpleNamespace(system_prompt="Speak as Socrates.", temperature=0.7, max_tokens=256)
        await service.call_llm_api("Discussion topic: justice", agent_config)

        self.assertEqual(captured["messages"][0], {"role": "system", "content": "Speak as Socrates."})
        self.assertEqual(captured["messages"][1], {"role": "user", "content": "Discussion topic: justice"})


if __name__ == "__main__":
    unittest.main()
