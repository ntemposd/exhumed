import unittest
from types import SimpleNamespace
from uuid import uuid4

from backend.services.turn_workflow import TurnWorkflowService


class TurnWorkflowServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_prepare_turn_inputs_extracts_previous_response(self):
        service = TurnWorkflowService(
            fetch_agent_config=self._fetch_agent_config,
            fetch_context_messages=self._fetch_context_messages,
            get_agent_context_matches=lambda topic, agent_id: [{"data": topic, "agent_id": agent_id}],
            sanitize_generated_message=lambda message, display_name: message,
            save_latest_execution_metrics=self._noop_async,
            persist_session_telemetry=self._noop_async,
            save_message_to_storage=self._save_message_to_storage,
            calculate_entropy=lambda current, previous: 0.5,
            build_telemetry=lambda **kwargs: kwargs,
        )

        agent_config, context_messages, matches, previous_response = await service.prepare_turn_inputs(
            session_id=uuid4(),
            agent_id="agt_001",
            topic="virtue",
        )

        self.assertEqual(agent_config.display_name, "Socrates")
        self.assertEqual(len(context_messages), 1)
        self.assertEqual(matches[0]["data"], "virtue")
        self.assertEqual(previous_response, "Previous turn")

    async def test_finalize_generated_turn_sanitizes_and_persists(self):
        stored_messages = []

        async def save_message_to_storage(**kwargs):
            stored_messages.append(kwargs)
            return {"id": "message-1", **kwargs}

        metrics = SimpleNamespace(generation_duration_ms=150, network_rtt_ms=90)
        service = TurnWorkflowService(
            fetch_agent_config=self._fetch_agent_config,
            fetch_context_messages=self._fetch_context_messages,
            get_agent_context_matches=lambda topic, agent_id: [],
            sanitize_generated_message=lambda message, display_name: message.replace(f"{display_name}: ", ""),
            save_latest_execution_metrics=self._noop_async,
            persist_session_telemetry=self._noop_async,
            save_message_to_storage=save_message_to_storage,
            calculate_entropy=lambda current, previous: 0.25,
            build_telemetry=lambda **kwargs: kwargs,
        )

        message, telemetry, stored_message = await service.finalize_generated_turn(
            session_id=uuid4(),
            agent_id="agt_001",
            display_name="Socrates",
            generated_message="Socrates: Temperance matters.",
            topic="virtue",
            turn_number=2,
            previous_response="Earlier response",
            vector_telemetry={"used": True},
            execution_metrics=metrics,
        )

        self.assertEqual(message, "Temperance matters.")
        self.assertEqual(telemetry["entropy"], 0.25)
        self.assertEqual(telemetry["latency_ms"], 150)
        self.assertEqual(stored_messages[0]["message"], "Temperance matters.")
        self.assertEqual(stored_message["id"], "message-1")

    async def _fetch_agent_config(self, agent_id):
        return SimpleNamespace(agent_id=agent_id, display_name="Socrates")

    async def _fetch_context_messages(self, session_id, limit):
        return [{"message": "Previous turn", "display_name": "Socrates", "agent_id": "agt_001"}]

    async def _save_message_to_storage(self, **kwargs):
        return kwargs

    async def _noop_async(self, *args, **kwargs):
        return None