import unittest

from backend.services.session_service import SessionService


class SessionServicePromptTests(unittest.TestCase):
    def test_build_context_prompt_renders_enriched_context_as_numbered_blocks(self):
        service = SessionService(
            redis_client=None,
            database_service=None,
            run_blocking_io=None,
            decode_value=lambda value: value,
            export_session_pdf=None,
            logger=None,
        )

        prompt = service.build_context_prompt(
            topic="justice",
            context_messages=[],
            agent_config=type("AgentConfig", (), {"system_prompt": "Speak as Socrates."})(),
            agent_context_matches=[
                {"data": "First paragraph.\n\nSecond paragraph."},
                {"data": "Third paragraph."},
            ],
        )

        self.assertIn("Relevant historical speaker context:\n\n[1] First paragraph.\n\nSecond paragraph.\n\n[2] Third paragraph.", prompt)
        self.assertNotIn("- First paragraph.", prompt)