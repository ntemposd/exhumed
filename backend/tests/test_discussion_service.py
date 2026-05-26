import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from backend.services.discussion_service import DiscussionService


def _model_with_dump(**kwargs):
    return SimpleNamespace(model_dump_json=lambda: "{}", **kwargs)


class DiscussionServiceDebateFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_capture_provider_request_uses_system_and_user_messages(self):
        captures = []

        async def save_prompt_capture(payload):
            captures.append(payload)

        llm_service = SimpleNamespace(
            build_provider_request=lambda **kwargs: {
                "request_url": "https://api.example.com/v1/chat/completions",
                "body": {
                    "model": "demo-model",
                    "messages": kwargs["messages"],
                    "temperature": 0.7,
                    "max_tokens": 256,
                    "stream": kwargs["stream"],
                },
            }
        )
        service = DiscussionService(
            turn_workflow_service=SimpleNamespace(),
            session_service=SimpleNamespace(),
            llm_service=llm_service,
            fetch_agent_config=None,
            save_latest_execution_metrics=None,
            save_prompt_capture=save_prompt_capture,
            process_turn_response_model=lambda **kwargs: kwargs,
            process_turn_stream_chunk_model=_model_with_dump,
            process_turn_stream_status_model=_model_with_dump,
            process_turn_stream_final_model=_model_with_dump,
            generate_response_model=lambda **kwargs: kwargs,
            streaming_response_factory=lambda *args, **kwargs: None,
            vector_telemetry_model=lambda **kwargs: kwargs,
            logger=SimpleNamespace(info=lambda *args, **kwargs: None, warning=lambda *args, **kwargs: None, error=lambda *args, **kwargs: None),
            utcnow=lambda: None,
        )

        await service._capture_provider_request(
            route="process-turn",
            session_id=uuid4(),
            topic="justice",
            turn_number=1,
            agent_config=SimpleNamespace(agent_id="agt_001", display_name="Socrates", system_prompt="Speak as Socrates.", max_tokens=256),
            prompt="Discussion topic: justice",
            context_messages=[],
            agent_context_matches=[],
            temperature_override=0.7,
            stream=False,
        )

        self.assertEqual(captures[0]["provider_request"]["body"]["messages"][0], {"role": "system", "content": "Speak as Socrates."})
        self.assertEqual(captures[0]["provider_request"]["body"]["messages"][1], {"role": "user", "content": "Discussion topic: justice"})

    async def test_process_turn_persists_session_topic_before_generation(self):
        save_session_topic = AsyncMock()
        session_service = SimpleNamespace(
            save_session_topic=save_session_topic,
            summarize_vector_telemetry=lambda matches, build_vector_telemetry: {"used": bool(matches)},
            build_context_prompt=lambda *args, **kwargs: "Discussion topic: justice",
        )
        turn_workflow_service = SimpleNamespace(
            prepare_turn_inputs=AsyncMock(return_value=(SimpleNamespace(display_name="Socrates"), [], [], "")),
            finalize_generated_turn=AsyncMock(return_value=("Grounded answer.", {"entropy": 0.0}, {"id": uuid4()})),
        )
        llm_service = SimpleNamespace(call_llm_api=AsyncMock(return_value=("Grounded answer.", {"duration": 1})))
        service = DiscussionService(
            turn_workflow_service=turn_workflow_service,
            session_service=session_service,
            llm_service=llm_service,
            fetch_agent_config=None,
            save_latest_execution_metrics=None,
            save_prompt_capture=None,
            process_turn_response_model=lambda **kwargs: kwargs,
            process_turn_stream_chunk_model=_model_with_dump,
            process_turn_stream_status_model=_model_with_dump,
            process_turn_stream_final_model=_model_with_dump,
            generate_response_model=lambda **kwargs: kwargs,
            streaming_response_factory=lambda *args, **kwargs: None,
            vector_telemetry_model=lambda **kwargs: kwargs,
            logger=SimpleNamespace(info=lambda *args, **kwargs: None, warning=lambda *args, **kwargs: None, error=lambda *args, **kwargs: None),
            utcnow=lambda: None,
        )

        request = SimpleNamespace(session_id=uuid4(), agent_id="agt_001", topic="justice", turn_number=None, temperature=None)
        await service.process_turn(request)

        save_session_topic.assert_awaited_once_with(request.session_id, "justice")

    async def test_process_turn_stream_persists_session_topic_and_uses_system_message(self):
        save_session_topic = AsyncMock()
        stream_messages = {}

        async def fake_stream_llm_api(messages, agent_config, temperature_override=None, on_complete=None, on_retry=None, **kwargs):
            stream_messages["messages"] = messages
            if on_complete is not None:
                await on_complete("Grounded answer.", {"duration": 1})
            if False:
                yield ""

        session_service = SimpleNamespace(
            save_session_topic=save_session_topic,
            summarize_vector_telemetry=lambda matches, build_vector_telemetry: {"used": bool(matches)},
            build_context_prompt=lambda *args, **kwargs: "Discussion topic: justice",
        )
        turn_workflow_service = SimpleNamespace(
            prepare_turn_inputs=AsyncMock(return_value=(SimpleNamespace(display_name="Socrates", system_prompt="Speak as Socrates."), [], [], "")),
            finalize_generated_turn=AsyncMock(return_value=("Grounded answer.", {"entropy": 0.0}, {"id": uuid4()})),
        )
        llm_service = SimpleNamespace(stream_llm_api=fake_stream_llm_api)
        service = DiscussionService(
            turn_workflow_service=turn_workflow_service,
            session_service=session_service,
            llm_service=llm_service,
            fetch_agent_config=None,
            save_latest_execution_metrics=None,
            save_prompt_capture=None,
            process_turn_response_model=lambda **kwargs: kwargs,
            process_turn_stream_chunk_model=_model_with_dump,
            process_turn_stream_status_model=_model_with_dump,
            process_turn_stream_final_model=_model_with_dump,
            generate_response_model=lambda **kwargs: kwargs,
            streaming_response_factory=lambda iterator, media_type=None, **kwargs: iterator,
            vector_telemetry_model=lambda **kwargs: kwargs,
            logger=SimpleNamespace(info=lambda *args, **kwargs: None, warning=lambda *args, **kwargs: None, error=lambda *args, **kwargs: None),
            utcnow=lambda: None,
        )

        request = SimpleNamespace(session_id=uuid4(), agent_id="agt_001", topic="justice", turn_number=None, temperature=None)
        stream = await service.process_turn_stream(request)
        async for _ in stream:
            pass

        save_session_topic.assert_awaited_once_with(request.session_id, "justice")
        self.assertEqual(stream_messages["messages"][0], {"role": "system", "content": "Speak as Socrates."})
        self.assertEqual(stream_messages["messages"][1], {"role": "user", "content": "Discussion topic: justice"})


if __name__ == "__main__":
    unittest.main()