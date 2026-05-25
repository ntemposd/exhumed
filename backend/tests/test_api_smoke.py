import importlib
import os
import tempfile
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient


os.environ.setdefault("UPSTASH_REDIS_REST_URL", "https://example-redis.upstash.io")
os.environ.setdefault("UPSTASH_REDIS_REST_TOKEN", "test-token")
os.environ.setdefault("UPSTASH_VECTOR_REST_URL", "https://example-vector.upstash.io")
os.environ.setdefault("UPSTASH_VECTOR_REST_TOKEN", "test-token")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("BACKEND_STARTUP_READINESS_MODE", "off")

backend_main = importlib.import_module("backend.main")
client = TestClient(backend_main.app)


class ApiSmokeTests(unittest.TestCase):
    def test_startup_readiness_runs_during_app_startup(self):
        readiness_mock = AsyncMock(
            return_value={
                "status": "OPTIMAL",
                "services": [
                    {"name": "Redis", "status": "ONLINE", "latency_ms": 1, "detail": None},
                    {"name": "Vector", "status": "ONLINE", "latency_ms": 1, "detail": None},
                    {"name": "Inference", "status": "ONLINE", "latency_ms": 1, "detail": None},
                ],
                "checked_at": "2026-05-07T00:00:00+00:00",
            }
        )
        observability = SimpleNamespace(
            set_shared_http_client=lambda client: None,
            check_services=readiness_mock,
        )
        services = dict(backend_main.app.state.services)
        services["observability_service"] = observability

        with patch.object(backend_main, "build_runtime_services", return_value=services), patch.dict(
            os.environ,
            {"BACKEND_STARTUP_READINESS_MODE": "strict"},
            clear=False,
        ):
            with TestClient(backend_main.create_app()):
                pass

        readiness_mock.assert_awaited_once()

    def test_startup_readiness_fails_fast_when_dependency_is_offline(self):
        readiness_mock = AsyncMock(
            return_value={
                "status": "DEGRADED",
                "services": [
                    {"name": "Redis", "status": "OFFLINE", "latency_ms": None, "detail": "timeout"},
                ],
                "checked_at": "2026-05-07T00:00:00+00:00",
            }
        )
        observability = SimpleNamespace(
            set_shared_http_client=lambda client: None,
            check_services=readiness_mock,
        )
        services = dict(backend_main.app.state.services)
        services["observability_service"] = observability

        with patch.object(backend_main, "build_runtime_services", return_value=services), patch.dict(
            os.environ,
            {"BACKEND_STARTUP_READINESS_MODE": "strict"},
            clear=False,
        ):
            with self.assertRaisesRegex(RuntimeError, "Startup readiness failed"):
                with TestClient(backend_main.create_app()):
                    pass

    def test_root_smoke(self):
        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["name"], "EXHUMED")
        self.assertIn("process_turn", payload["endpoints"])

    def test_request_id_header_is_returned(self):
        request_id = "req-test-123"

        response = client.get("/", headers={"X-Request-ID": request_id})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("X-Request-ID"), request_id)

    def test_session_topic_routes(self):
        session_id = str(uuid4())

        with patch.object(backend_main.session_service, "save_session_topic", AsyncMock()) as save_topic_mock, patch.object(
            backend_main.session_service,
            "fetch_session_topic",
            AsyncMock(return_value="AI governance"),
        ):
            response = client.post(f"/sessions/{session_id}/topic", json={"topic": "AI governance"})
            self.assertEqual(response.status_code, 200)
            save_topic_mock.assert_awaited_once()

            response = client.get(f"/sessions/{session_id}/topic")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["topic"], "AI governance")

    def test_agent_routes_smoke(self):
        register_mock = AsyncMock(return_value=None)
        list_mock = AsyncMock(return_value=[{"agent_id": "agt_001", "display_name": "Socrates"}])

        with patch.object(backend_main.agent_registry_service, "register_agent", register_mock), patch.object(
            backend_main.agent_registry_service,
            "list_agents",
            list_mock,
        ):
            register_response = client.post(
                "/agents/register",
                json={
                    "agent_id": "agt_001",
                    "display_name": "Socrates",
                    "system_prompt": "Speak plainly.",
                    "temperature": 0.7,
                    "max_tokens": 256,
                },
            )
            self.assertEqual(register_response.status_code, 200)
            self.assertEqual(register_response.json()["agent_id"], "agt_001")

            list_response = client.get("/agents")
            self.assertEqual(list_response.status_code, 200)
            self.assertEqual(list_response.json()["agents"][0]["display_name"], "Socrates")

    def test_generate_route_smoke(self):
        telemetry = backend_main.TelemetryData(
            entropy=0.0,
            latency_ms=120,
            word_count=2,
            vector=backend_main.VectorTelemetry(
                used=False,
                match_count=0,
                top_score=None,
                sources=[],
                chunk_ids=[],
                context_chars=0,
            ),
        )

        with patch.object(
            backend_main.discussion_service,
            "generate",
            AsyncMock(
                return_value=backend_main.GenerateResponse(
                    response="Temperance matters.",
                    telemetry=telemetry,
                    message_id=uuid4(),
                    turn_number=1,
                )
            ),
        ):
            response = client.post(
                "/generate",
                json={
                    "session_id": str(uuid4()),
                    "topic": "Virtue",
                    "agent_id": "agt_001",
                    "previous_response": None,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["response"], "Temperance matters.")
        self.assertEqual(payload["telemetry"]["latency_ms"], 120)

    def test_process_turn_route_smoke(self):
        execution_metrics = backend_main.ExecutionMetrics(
            generation_duration_ms=90,
            prompt_tokens=8,
            completion_tokens=10,
            total_tokens=18,
            tokens_per_second=18.0,
            queue_time_ms=None,
            prompt_time_ms=None,
            ttft_ms=None,
            network_rtt_ms=60,
            provider="llm",
            updated_at=datetime.now(timezone.utc),
        )
        telemetry = backend_main.TelemetryData(
            entropy=0.2,
            latency_ms=90,
            word_count=3,
            vector=backend_main.VectorTelemetry(
                used=False,
                match_count=0,
                top_score=None,
                sources=[],
                chunk_ids=[],
                context_chars=0,
            ),
        )
        message_id = uuid4()

        with patch.object(
            backend_main.discussion_service,
            "process_turn",
            AsyncMock(
                return_value=backend_main.ProcessTurnResponse(
                    message_id=message_id,
                    agent_id="agt_001",
                    display_name="Socrates",
                    message="Ask better questions.",
                    turn_number=1,
                    created_at=datetime.now(timezone.utc),
                    telemetry=telemetry,
                    execution_metrics=execution_metrics,
                )
            ),
        ):
            response = client.post(
                "/process-turn",
                json={
                    "session_id": str(uuid4()),
                    "topic": "Virtue",
                    "agent_id": "agt_001",
                    "temperature": 0.8,
                    "turn_number": None,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["message"], "Ask better questions.")
        self.assertEqual(payload["telemetry"]["entropy"], 0.2)

    def test_process_turn_validation_error_surfaces_details(self):
        response = client.post(
            "/process-turn",
            json={
                "session_id": "legacy-session-id",
                "topic": "Virtue",
                "agent_id": "agt_001",
            },
        )

        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertIn("detail", payload)
        self.assertTrue(any("session_id" in "/".join(str(part) for part in error["loc"]) for error in payload["detail"]))

    def test_services_status_route_smoke(self):
        status_mock = AsyncMock(
            return_value={
                "status": "OPTIMAL",
                "services": [{"name": "Redis", "status": "ONLINE", "latency_ms": 12, "detail": None}],
                "checked_at": "2026-05-07T00:00:00+00:00",
            }
        )

        with patch.object(backend_main.observability_service, "check_services", status_mock):
            response = client.get("/services-status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "OPTIMAL")

    def test_export_pdf_route_smoke(self):
        session_id = str(uuid4())
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
            handle.write(b"%PDF-1.4\n%test\n")
            temp_pdf_path = handle.name

        with patch.object(
            backend_main.session_service,
            "export_pdf_file",
            AsyncMock(return_value=temp_pdf_path),
        ) as export_pdf_mock:
            response = client.get(f"/export-pdf/{session_id}?topic=Current%20Topic")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/pdf")
        export_pdf_mock.assert_awaited_once_with(UUID(session_id), topic="Current Topic")


if __name__ == "__main__":
    unittest.main()