import sys
import types
import unittest

dotenv_module = types.ModuleType("dotenv")
dotenv_module.load_dotenv = lambda *args, **kwargs: None
sys.modules.setdefault("dotenv", dotenv_module)

from backend.scripts.query_vector_stats import build_agent_filter, format_summary_report, summarize_matches


class QueryVectorStatsTests(unittest.TestCase):
    def test_build_agent_filter_escapes_quotes(self):
        self.assertEqual(
            build_agent_filter("agt_'01"),
            "agent_id = 'agt_\\'01'",
        )

    def test_summarize_matches_groups_by_agent_and_source(self):
        matches = [
            {
                "score": 0.98,
                "metadata": {
                    "agent_id": "agt_003",
                    "speaker_name": "Sun Tzu",
                    "source_title": "The Art of War",
                },
                "data": "Plan well.",
            },
            {
                "score": 0.91,
                "metadata": {
                    "agent_id": "agt_003",
                    "speaker_name": "Sun Tzu",
                    "source_title": "The Art of War",
                },
                "data": "Move when advantageous.",
            },
            {
                "score": 0.88,
                "metadata": {
                    "agent_id": "agt_002",
                    "speaker_name": "Steve Jobs",
                    "source_title": "Stanford Commencement Address",
                },
                "data": "Stay hungry, stay foolish.",
            },
        ]

        summaries = summarize_matches(matches)

        self.assertEqual(len(summaries), 2)
        jobs_summary = summaries[0]
        self.assertEqual(jobs_summary["agent_id"], "agt_002")
        self.assertEqual(jobs_summary["chunk_count"], 1)
        self.assertEqual(jobs_summary["avg_chars"], 26.0)

        sun_tzu_summary = summaries[1]
        self.assertEqual(sun_tzu_summary["agent_id"], "agt_003")
        self.assertEqual(sun_tzu_summary["chunk_count"], 2)
        self.assertEqual(sun_tzu_summary["source_stats"][0]["source_title"], "The Art of War")
        self.assertEqual(sun_tzu_summary["source_stats"][0]["max_chars"], 23)
        self.assertEqual(sun_tzu_summary["source_stats"][0]["min_chars"], 10)

    def test_format_summary_report_includes_requested_fields(self):
        summaries = [
            {
                "agent_id": "agt_013",
                "speaker_name": "Nikola Tesla",
                "source_stats": [
                    {
                        "source_title": "My Inventions",
                        "source_volume": "",
                        "source_chapter": "",
                        "source_slug": "my-inventions",
                        "chunk_count": 3,
                        "avg_chars": 412.7,
                        "max_chars": 480,
                        "min_chars": 355,
                    }
                ],
                "chunk_count": 3,
                "avg_chars": 412.7,
                "max_chars": 480,
                "min_chars": 355,
                "top_score": 0.9234,
            }
        ]

        report = format_summary_report("Query: electricity and invention", summaries, total_matches=3)

        self.assertIn("Query: electricity and invention", report)
        self.assertIn("Agent: Nikola Tesla (agt_013)", report)
        self.assertIn("My Inventions [my-inventions]", report)
        self.assertIn("Chunks: 3", report)
        self.assertIn("Avg chars: 412.7", report)
        self.assertIn("Max chars: 480", report)
        self.assertIn("Min chars: 355", report)
        self.assertIn("Per-source stats:", report)

    def test_format_summary_report_supports_full_scan_label(self):
        report = format_summary_report("Mode: full index scan", [], total_matches=0)

        self.assertIn("Mode: full index scan", report)
        self.assertIn("Matched chunks: 0", report)
        self.assertIn("No matching chunks found.", report)


if __name__ == "__main__":
    unittest.main()