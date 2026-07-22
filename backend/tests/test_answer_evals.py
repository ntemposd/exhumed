import unittest

from backend.utils.answer_evals import (
    build_answer_eval_scores,
    join_retrieval_context,
    score_grounding,
    score_persona,
)
from backend.utils.text_metrics import calculate_jaccard_entropy


class AnswerEvalTests(unittest.TestCase):
    def test_join_retrieval_context_concatenates_chunk_text(self):
        text = join_retrieval_context(
            [
                {"data": "Virtue requires examination."},
                {"data": ""},
                {"data": "Courage is a mean."},
                {"score": 0.9},
            ]
        )
        self.assertEqual(text, "Virtue requires examination.\nCourage is a mean.")

    def test_score_grounding_zero_without_retrieval(self):
        self.assertEqual(score_grounding(None, used=False), 0.0)
        self.assertEqual(score_grounding(0.95, used=False), 0.0)
        self.assertEqual(score_grounding(None, used=True), 0.0)

    def test_score_grounding_normalizes_threshold_band(self):
        self.assertEqual(score_grounding(0.60, used=True), 0.0)
        self.assertEqual(score_grounding(0.80, used=True), 0.5)
        self.assertEqual(score_grounding(1.0, used=True), 1.0)
        self.assertEqual(score_grounding(0.50, used=True), 0.0)

    def test_score_persona_zero_without_context(self):
        self.assertEqual(score_persona("Temperance matters.", ""), 0.0)
        self.assertEqual(score_persona("", "Temperance matters."), 0.0)

    def test_score_persona_high_when_answer_matches_context(self):
        context = "Temperance matters when pursuing virtue and wisdom."
        answer = "Temperance matters when pursuing virtue and wisdom."
        self.assertGreater(score_persona(answer, context), 0.9)

    def test_score_persona_low_when_answer_unrelated(self):
        context = "Naval strategy depends on weather and supply lines."
        answer = "Virtue requires careful examination of one's soul."
        self.assertLess(score_persona(answer, context), 0.2)

    def test_build_answer_eval_scores_composes_all_metrics(self):
        context = "Temperance matters when pursuing virtue."
        answer = "Temperance matters when pursuing virtue."
        previous = "Temperance matters when pursuing virtue."
        debate = calculate_jaccard_entropy(answer, previous)

        scores = build_answer_eval_scores(
            answer=answer,
            retrieval_context_text=context,
            top_score=1.0,
            used=True,
            debate_entropy=debate,
        )

        self.assertEqual(scores["grounding"], 1.0)
        self.assertGreater(scores["persona"], 0.9)
        self.assertEqual(scores["debate"], 0.0)

    def test_build_answer_eval_scores_no_retrieval_and_divergent_debate(self):
        answer = "Courage decides campaigns through bold decisive action."
        previous = "Virtue requires quiet contemplation of eternal forms."
        debate = calculate_jaccard_entropy(answer, previous)

        scores = build_answer_eval_scores(
            answer=answer,
            retrieval_context_text="",
            top_score=None,
            used=False,
            debate_entropy=debate,
        )

        self.assertEqual(scores["grounding"], 0.0)
        self.assertEqual(scores["persona"], 0.0)
        self.assertGreater(scores["debate"], 0.7)


if __name__ == "__main__":
    unittest.main()
