import unittest

from backend.evals.suite import failing_cases_for_agent, filter_cases, summarize_results


class EvalSuiteTests(unittest.TestCase):
    def test_filter_cases_by_agent_and_id(self):
        cases = [
            {"id": "a", "agent_id": "agt_001"},
            {"id": "b", "agent_id": "agt_003"},
            {"id": "c", "agent_id": "agt_001"},
        ]
        self.assertEqual(
            [case["id"] for case in filter_cases(cases, agent_id="agt_001")],
            ["a", "c"],
        )
        self.assertEqual(
            [case["id"] for case in filter_cases(cases, case_ids=["b"])],
            ["b"],
        )

    def test_summarize_results_pass_and_fail(self):
        passing = summarize_results(
            [
                {"judge": {"faithfulness": 4, "persona": 4}},
                {"judge": {"faithfulness": 5, "persona": 4}},
            ]
        )
        self.assertTrue(passing["passed"])

        failing = summarize_results(
            [
                {"judge": {"faithfulness": 4, "persona": 2}},
                {"judge": {"faithfulness": 4, "persona": 4}},
            ]
        )
        self.assertFalse(failing["passed"])
        self.assertTrue(any("min_persona" in item for item in failing["failures"]))

    def test_failing_cases_for_agent(self):
        report = {
            "cases": [
                {"id": "ok", "agent_id": "agt_001", "judge": {"faithfulness": 4, "persona": 4}},
                {"id": "bad", "agent_id": "agt_001", "judge": {"faithfulness": 2, "persona": 4}},
                {"id": "other", "agent_id": "agt_003", "judge": {"faithfulness": 1, "persona": 1}},
            ]
        }
        failing = failing_cases_for_agent(report, "agt_001")
        self.assertEqual([case["id"] for case in failing], ["bad"])


if __name__ == "__main__":
    unittest.main()
