import unittest
from datetime import datetime, timezone

from backend.services.observability import ObservabilityService


class FakeExecutionMetricsModel:
    @staticmethod
    def model_validate(payload):
        return payload


class FakeRedis:
    def __init__(self):
        self.values = {}

    def set(self, key, value):
        self.values[key] = value

    def get(self, key):
        return self.values.get(key)

    def ping(self):
        return True


class FakeVectorIndex:
    def info(self):
        return {"ok": True}


class FakeMetrics:
    def model_dump_json(self):
        return '{"provider":"llm","network_rtt_ms":40}'


class FakeResponse:
    def raise_for_status(self):
        return None


class FakeHttpClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, headers):
        return FakeResponse()


async def run_blocking_io(func, *args, **kwargs):
    return func(*args, **kwargs)


class ObservabilityServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.redis = FakeRedis()
        self.vector_index = FakeVectorIndex()
        self.logger = type("Logger", (), {"warning": lambda *args, **kwargs: None})()
        self.service = ObservabilityService(
            redis_client=self.redis,
            vector_index=self.vector_index,
            decode_value=str,
            run_blocking_io=run_blocking_io,
            execution_metrics_model=FakeExecutionMetricsModel,
            llm_api_base_url="https://example-llm.test",
            llm_api_key="test-key",
            logger=self.logger,
            http_client_factory=lambda **kwargs: FakeHttpClient(),
            perf_counter=lambda: 10.0,
            utcnow=lambda: datetime(2026, 5, 7, tzinfo=timezone.utc),
        )

    async def test_check_services_returns_expected_shape(self):
        payload = await self.service.check_services()

        self.assertEqual(payload["status"], "OPTIMAL")
        self.assertEqual(len(payload["services"]), 3)
        self.assertEqual(payload["services"][0]["name"], "Redis")

    async def test_save_and_fetch_latest_execution_metrics_round_trip(self):
        self.service.save_latest_execution_metrics(FakeMetrics())

        payload = self.service.fetch_latest_execution_metrics()

        self.assertEqual(payload["provider"], "llm")
        self.assertEqual(payload["network_rtt_ms"], 40)


if __name__ == "__main__":
    unittest.main()