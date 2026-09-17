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
from app.services.provider_guard import provider_access_context
from app.services.release_ledger import (
    read_release_events,
    release_ledger_context,
    summarize_release_events,
)
from scripts.run_deepseek_release_batch import _atomic_create_json, _atomic_replace_json
from scripts.run_deepseek_release_batch import _sync_process_ledger


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
    def test_release_lock_create_is_exclusive_and_final_update_is_atomic(self) -> None:
        with TemporaryDirectory() as directory:
            lock = Path(directory) / "deepseek-release-lock-v3.0.1-final-test.json"
            running = {"releaseId": "release-test", "status": "RUNNING"}
            _atomic_create_json(lock, running)
            with self.assertRaises(FileExistsError):
                _atomic_create_json(lock, running)
            _atomic_replace_json(lock, {"releaseId": "release-test", "status": "PASSED"})
            self.assertEqual("PASSED", json.loads(lock.read_text(encoding="utf-8"))["status"])

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
                        with provider_access_context(
                            mode="mock",
                            release_id="fixture-release",
                            batch_id="fake-batch",
                            ledger_path=str(ledger),
                            runtime_commit="a" * 40,
                            authorized=True,
                            allow_mock=True,
                        ):
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

    def test_process_ledger_sync_binds_raw_events_and_fails_without_path(self) -> None:
        with TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "release.jsonl"
            with patch.dict(
                "os.environ",
                {
                    "MALL_RELEASE_LEDGER_PATH": str(ledger_path),
                    "MALL_RUNTIME_COMMIT": "a" * 40,
                    "MALL_PROMPT_VERSION": "test_prompt",
                    "MALL_SCHEMA_VERSION": "test_schema",
                },
                clear=False,
            ):
                with release_ledger_context(batch_id="sync-batch", path=ledger_path, source="test"):
                    from app.services.release_ledger import append_release_event

                    append_release_event(
                        event_type="provider_request",
                        operation="fake.decide",
                        outcome="succeeded",
                        prompt_tokens=2,
                        completion_tokens=3,
                        total_tokens=5,
                    )
                    append_release_event(
                        event_type="scenario",
                        operation="fake.scenario",
                        outcome="failed",
                        failure_class="scenario_failure",
                        scenario="ledger_contract",
                        stage="test",
                        failure_code="scenario_assertion_failure",
                    )
                ledger = {"batchId": "sync-batch"}
                self.assertTrue(_sync_process_ledger(ledger))
                self.assertEqual(1, ledger["providerRequests"])
                self.assertEqual(1, ledger["successfulRequests"])
                self.assertEqual(5, ledger["totalTokens"])
                self.assertEqual(1, ledger["scenarioFailures"])
                self.assertTrue(ledger["ledgerReconciled"])

            with patch.dict("os.environ", {}, clear=True):
                ledger = {"batchId": "sync-batch"}
                self.assertFalse(_sync_process_ledger(ledger))
                self.assertFalse(ledger["ledgerReconciled"])
                self.assertEqual("ledger_mismatch", ledger["failureCategory"])


if __name__ == "__main__":
    unittest.main()
