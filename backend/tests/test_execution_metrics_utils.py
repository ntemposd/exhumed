import unittest

import httpx

from backend.utils.execution_metrics import build_stream_execution_metrics, extract_execution_metrics


class ExecutionMetricsRecord:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class ExecutionMetricsUtilsTests(unittest.TestCase):
    def test_extract_execution_metrics_maps_provider_usage(self):
        metrics = extract_execution_metrics(
            {
                "usage": {
                    "prompt_tokens": "10",
                    "completion_tokens": 20,
                    "total_tokens": 30,
                    "queue_time": 0.1,
                    "prompt_time": 0.05,
                    "completion_time": 0.5,
                }
            },
            httpx.Headers({}),
            80,
            build_metrics=ExecutionMetricsRecord,
        )

        self.assertEqual(metrics.prompt_tokens, 10)
        self.assertEqual(metrics.completion_tokens, 20)
        self.assertEqual(metrics.total_tokens, 30)
        self.assertEqual(metrics.queue_time_ms, 100)
        self.assertEqual(metrics.prompt_time_ms, 50)
        self.assertEqual(metrics.generation_duration_ms, 500)
        self.assertEqual(metrics.tokens_per_second, 40.0)

    def test_build_stream_execution_metrics_estimates_missing_fields(self):
        metrics = build_stream_execution_metrics(
            usage={},
            headers=httpx.Headers({}),
            network_rtt_ms=60,
            request_started=10.0,
            first_token_at=10.2,
            generated_message="One two three four",
            build_metrics=ExecutionMetricsRecord,
            monotonic_now=lambda: 10.6,
        )

        self.assertEqual(metrics.generation_duration_ms, 599)
        self.assertEqual(metrics.completion_tokens, 4)
        self.assertEqual(metrics.total_tokens, 4)
        self.assertEqual(metrics.ttft_ms, 199)
        self.assertEqual(metrics.tokens_per_second, 6.68)


if __name__ == "__main__":
    unittest.main()