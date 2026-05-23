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

    def test_build_context_prompt_uses_grounded_retrieval_guidance_without_embedded_system_prompt(self):
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
            agent_context_matches=[{"data": "The unexamined life is not worth living."}],
        )

        self.assertTrue(prompt.startswith("Discussion topic: justice\n"))
        self.assertNotIn("Speak as Socrates.", prompt)
        self.assertIn("Your response must be grounded in the passages above", prompt)
        self.assertIn("Do not draw on general or popular knowledge about yourself", prompt)

    def test_build_context_prompt_adds_fallback_guidance_when_no_matches_exist(self):
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
            agent_context_matches=[],
        )

        self.assertIn("No source passages were retrieved for this turn.", prompt)
        self.assertIn("Do not speculate beyond what is historically established.", prompt)
        self.assertNotIn("Speak as Socrates.", prompt)

    def test_build_context_prompt_keeps_recent_discussion_without_embedded_system_prompt(self):
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
            context_messages=[
                {
                    "turn_number": 2,
                    "display_name": "Plato",
                    "agent_id": "agt_002",
                    "message": "Justice orders the soul.",
                }
            ],
            agent_config=type("AgentConfig", (), {"system_prompt": "Speak as Socrates."})(),
            agent_context_matches=None,
        )

        self.assertIn("Recent discussion context (latest turns):", prompt)
        self.assertIn("Turn 2, Plato: Justice orders the soul.", prompt)
        self.assertNotIn("Speak as Socrates.", prompt)

