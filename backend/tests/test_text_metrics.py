import unittest

from backend.utils.text_metrics import calculate_jaccard_entropy, clean_text_for_similarity


class TextMetricsTests(unittest.TestCase):
    def test_clean_text_for_similarity_normalizes_case_and_punctuation(self):
        tokens = clean_text_for_similarity("Hello, HELLO! world?")

        self.assertEqual(tokens, {"hello", "world"})

    def test_calculate_jaccard_entropy_returns_zero_for_identical_text(self):
        self.assertEqual(calculate_jaccard_entropy("Hello world", "Hello world"), 0.0)

    def test_calculate_jaccard_entropy_returns_full_entropy_for_disjoint_text(self):
        self.assertEqual(calculate_jaccard_entropy("Hello", "Goodbye"), 1.0)


if __name__ == "__main__":
    unittest.main()