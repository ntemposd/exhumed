import unittest

from backend.services.session_service import SessionService
from backend.utils.prompt_budget import PromptBudget


class SessionServicePromptBudgetTests(unittest.TestCase):
    def test_build_context_prompt_truncates_source_and_history_blocks(self):
        service = SessionService(
            redis_client=None,
            database_service=None,
            run_blocking_io=None,
            decode_value=lambda value: value,
            export_session_pdf=None,
            logger=None,
            prompt_budget=PromptBudget(
                max_source_chunk_chars=40,
                max_context_turn_chars=24,
            ),
        )

        prompt = service.build_context_prompt(
            topic="justice",
            context_messages=[
                {
                    "turn_number": 2,
                    "display_name": "Plato",
                    "agent_id": "agt_002",
                    "message": "Justice orders the soul and keeps the city aligned with virtue.",
                }
            ],
            agent_config=type("AgentConfig", (), {"system_prompt": "Speak as Socrates."})(),
            agent_context_matches=[{"data": "The unexamined life is not worth living for any human being in this city."}],
        )

        self.assertIn("[1] The unexamined life", prompt)
        self.assertNotIn("for any human being in this city.", prompt)
        self.assertIn("Turn 2, Plato: Justice orders", prompt)
        self.assertNotIn("keeps the city aligned with virtue.", prompt)


if __name__ == "__main__":
    unittest.main()
