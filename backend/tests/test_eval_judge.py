import unittest

from backend.evals.judge import (
    build_judge_user_prompt,
    normalize_score_1_to_5,
    parse_judge_response,
)


class EvalJudgeTests(unittest.TestCase):
    def test_normalize_score_maps_band(self):
        self.assertEqual(normalize_score_1_to_5(1), 0.0)
        self.assertEqual(normalize_score_1_to_5(3), 0.5)
        self.assertEqual(normalize_score_1_to_5(5), 1.0)

    def test_parse_judge_response_accepts_raw_json(self):
        result = parse_judge_response(
            """
            {
              "faithfulness": 4,
              "persona": 5,
              "faithfulness_notes": "Mostly grounded",
              "persona_notes": "Strong Socratic voice",
              "unsupported_claims": ["invented decree"]
            }
            """
        )
        self.assertEqual(result.faithfulness, 4)
        self.assertEqual(result.persona, 5)
        self.assertEqual(result.unsupported_claims, ["invented decree"])
        self.assertEqual(result.as_telemetry_dict()["persona"], 1.0)

    def test_parse_judge_response_accepts_fenced_json_and_clamps(self):
        result = parse_judge_response(
            """Here you go:
```json
{"faithfulness": 9, "persona": 0, "faithfulness_notes": "x", "persona_notes": "y", "unsupported_claims": []}
```
"""
        )
        self.assertEqual(result.faithfulness, 5)
        self.assertEqual(result.persona, 1)

    def test_parse_judge_response_rejects_empty(self):
        with self.assertRaises(ValueError):
            parse_judge_response("   ")

    def test_build_judge_user_prompt_includes_core_fields(self):
        prompt = build_judge_user_prompt(
            agent_id="agt_001",
            display_name="Socrates",
            topic="Virtue",
            system_prompt="Speak as Socrates.",
            retrieved_context="Examination of life.",
            previous_response="",
            answer="The unexamined life is not worth living.",
        )
        self.assertIn("Socrates", prompt)
        self.assertIn("Virtue", prompt)
        self.assertIn("Examination of life.", prompt)
        self.assertIn("unexamined life", prompt)
        self.assertIn("first turn", prompt)


if __name__ == "__main__":
    unittest.main()
