import unittest
from uuid import uuid4

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
        self.assertIn("Ground your reply in the passages above", prompt)
        self.assertIn("Do not use popular knowledge beyond what the passages establish", prompt)

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

        self.assertIn("Recent discussion context (for awareness only — do NOT echo or mirror):", prompt)
        self.assertIn("Turn 2, Plato: Justice orders the soul.", prompt)
        self.assertNotIn("Speak as Socrates.", prompt)


class SessionServicePdfExportTests(unittest.IsolatedAsyncioTestCase):
    async def test_export_pdf_file_prefers_explicit_topic_over_saved_topic(self):
        captured = {}

        def export_session_pdf(messages, session_id, *, logger=None):
            captured["messages"] = messages
            captured["session_id"] = session_id
            return "fake.pdf"

        service = SessionService(
            redis_client=None,
            database_service=None,
            run_blocking_io=None,
            decode_value=lambda value: value,
            export_session_pdf=export_session_pdf,
            logger=None,
        )

        service.fetch_session_topic = lambda session_id: self._awaitable("Past Topic")
        service.fetch_session_messages = lambda session_id: self._awaitable(
            [
                {"topic": "Past Topic", "message": "Older debate", "turn_number": 1},
                {"topic": "Current Topic", "message": "Visible debate", "turn_number": 2},
                {"topic": "current topic", "message": "Visible debate reply", "turn_number": 3},
            ]
        )

        session_id = uuid4()
        pdf_path = await service.export_pdf_file(session_id, topic="Current Topic")

        self.assertEqual(pdf_path, "fake.pdf")
        self.assertEqual(captured["session_id"], session_id)
        self.assertEqual([message["message"] for message in captured["messages"]], ["Visible debate", "Visible debate reply"])

    async def test_export_pdf_file_uses_only_active_topic_messages(self):
        captured = {}

        def export_session_pdf(messages, session_id, *, logger=None):
            captured["messages"] = messages
            captured["session_id"] = session_id
            return "fake.pdf"

        service = SessionService(
            redis_client=None,
            database_service=None,
            run_blocking_io=None,
            decode_value=lambda value: value,
            export_session_pdf=export_session_pdf,
            logger=None,
        )

        service.fetch_session_topic = lambda session_id: self._awaitable("Current Topic")
        service.fetch_session_messages = lambda session_id: self._awaitable(
            [
                {"topic": "Past Topic", "message": "Older debate", "turn_number": 1},
                {"topic": "Current Topic", "message": "Visible debate", "turn_number": 2},
                {"topic": "current topic", "message": "Visible debate reply", "turn_number": 3},
            ]
        )

        session_id = uuid4()
        pdf_path = await service.export_pdf_file(session_id)

        self.assertEqual(pdf_path, "fake.pdf")
        self.assertEqual(captured["session_id"], session_id)
        self.assertEqual([message["message"] for message in captured["messages"]], ["Visible debate", "Visible debate reply"])

    async def test_export_pdf_file_falls_back_to_full_session_when_no_active_topic_is_saved(self):
        captured = {}

        def export_session_pdf(messages, session_id, *, logger=None):
            captured["messages"] = messages
            return "fake.pdf"

        service = SessionService(
            redis_client=None,
            database_service=None,
            run_blocking_io=None,
            decode_value=lambda value: value,
            export_session_pdf=export_session_pdf,
            logger=None,
        )

        service.fetch_session_topic = lambda session_id: self._awaitable("")
        service.fetch_session_messages = lambda session_id: self._awaitable(
            [
                {"topic": "Past Topic", "message": "Older debate", "turn_number": 1},
                {"topic": "Current Topic", "message": "Visible debate", "turn_number": 2},
            ]
        )

        await service.export_pdf_file(uuid4())

        self.assertEqual([message["message"] for message in captured["messages"]], ["Older debate", "Visible debate"])

    async def _awaitable(self, value):
        return value

