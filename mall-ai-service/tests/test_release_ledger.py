"""Cross-process release ledger contract tests with a local fake provider."""

from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.services.llm_observability import capture_llm_metrics
from app.services.llm_service import LLMServiceError, generate_text
from app.services.release_ledger import (
    read_release_events,
    release_ledger_context,
    summarize_release_events,
)


class _FakeProviderHandler(BaseHTTPRequestHandler):
    calls = 0

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        type(self).calls += 1
        length = int(self.headers.get("content-length", "0"))
        self.rfile.read(length)
        if type(self).calls == 4:
            self.send_response(503)
            self.end_headers()
            return
        payload = {
            "choices": [{"message": {"content": "synthetic answer"}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        }
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_args: object) -> None:
        return None


class ReleaseLedgerTests(unittest.TestCase):
    def test_local_fake_provider_records_three_successes_and_one_failure(self) -> None:
        _FakeProviderHandler.calls = 0
        server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeProviderHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with TemporaryDirectory() as directory:
                ledger = Path(directory) / "release.jsonl"
                fake_settings = SimpleNamespace(
                    deepseek_api_key="fixture-only",
                    deepseek_model="deepseek-flash",
                    deepseek_base_url=f"http://127.0.0.1:{server.server_port}",
                    deepseek_timeout_seconds=2.0,
                )
                with patch("app.services.llm_service.settings", fake_settings):
                    with release_ledger_context(batch_id="fake-batch", path=ledger, source="test"):
                        with capture_llm_metrics(max_attempts=1, timeout_seconds=2.0):
                            for _ in range(3):
                                self.assertEqual("synthetic answer", generate_text("fixture input"))
                            with self.assertRaises(LLMServiceError):
                                generate_text("fixture input")
                events = read_release_events(ledger, batch_id="fake-batch")
                summary = summarize_release_events(events)
                self.assertEqual(4, summary["providerRequests"])
                self.assertEqual(3, summary["providerSuccesses"])
                self.assertEqual(1, summary["providerFailures"])
                self.assertEqual(0, summary["scenarioFailures"])
                self.assertEqual(0, summary["testFailures"])
                self.assertEqual(15, summary["totalTokens"])
                for event in events:
                    self.assertNotIn("prompt", event)
                    self.assertNotIn("messages", event)
                    self.assertNotIn("reasoning", event)
                    self.assertEqual("fake-batch", event["batchId"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
