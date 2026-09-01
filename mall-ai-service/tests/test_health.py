import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.readiness import get_readiness


class ReadinessTests(unittest.TestCase):
    def test_memory_backend_is_ready_without_external_calls(self) -> None:
        report = get_readiness(
            conversation_backend="memory",
            redis_factory=Mock(),
        )

        self.assertEqual({"status": "ok", "conversation_store": "memory"}, report)

    def test_redis_backend_reports_ready_after_ping(self) -> None:
        client = Mock()
        client.ping.return_value = True
        factory = Mock(return_value=client)

        report = get_readiness(
            conversation_backend="redis",
            redis_url="redis://demo",
            redis_factory=factory,
        )

        self.assertEqual({"status": "ok", "conversation_store": "redis"}, report)
        factory.assert_called_once()
        client.ping.assert_called_once()

    def test_redis_backend_fails_closed_when_ping_raises(self) -> None:
        factory = Mock(side_effect=RuntimeError("redis unavailable"))

        report = get_readiness(
            conversation_backend="redis",
            redis_factory=factory,
        )

        self.assertEqual({"status": "unavailable", "conversation_store": "redis"}, report)

    def test_invalid_backend_is_not_ready(self) -> None:
        report = get_readiness(conversation_backend="unknown")

        self.assertEqual(
            {"status": "unavailable", "conversation_store": "invalid_configuration"},
            report,
        )

    @patch("app.routers.health.get_readiness")
    def test_ready_endpoint_returns_503_for_unavailable_dependency(self, readiness) -> None:
        readiness.return_value = {"status": "unavailable", "conversation_store": "redis"}

        response = TestClient(app).get("/health/ready")

        self.assertEqual(503, response.status_code)
        self.assertEqual("unavailable", response.json()["detail"]["status"])

    @patch("app.routers.health.get_readiness")
    def test_ready_endpoint_returns_safe_success_summary(self, readiness) -> None:
        readiness.return_value = {"status": "ok", "conversation_store": "redis"}

        response = TestClient(app).get("/health/ready")

        self.assertEqual(200, response.status_code)
        self.assertEqual({"status": "ok", "conversation_store": "redis"}, response.json())


if __name__ == "__main__":
    unittest.main()
