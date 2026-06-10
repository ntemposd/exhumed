import unittest

from backend.utils.prompt_budget import PromptBudget, truncate_for_prompt


class PromptBudgetTests(unittest.TestCase):
    def test_truncate_for_prompt_keeps_short_text(self):
        self.assertEqual(truncate_for_prompt("Short passage.", 120), "Short passage.")

    def test_truncate_for_prompt_clips_long_text_with_ellipsis(self):
        text = "Alpha " + ("beta " * 40)
        clipped = truncate_for_prompt(text, 80)
        self.assertLessEqual(len(clipped), 82)
        self.assertTrue(clipped.endswith("…"))

    def test_default_budget_targets_8b_instant_tpm(self):
        budget = PromptBudget()
        self.assertEqual(budget.retrieval_top_k, 4)
        self.assertEqual(budget.debate_max_tokens, 384)


if __name__ == "__main__":
    unittest.main()
