"""Cross-process release ledger contract tests with a local fake provider."""

from __future__ import annotations

import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from unittest.mock import patch

import httpx

from app.services.llm_observability import capture_llm_metrics
from app.services.llm_service import LLMServiceError, generate_text
from app.services.provider_guard import provider_access_context
from app.services.release_ledger import (
    ReleaseLedgerBudgetError,
    ReleaseLedgerIntegrityError,
    reserve_provider_attempt,
    settle_provider_attempt,
    read_release_events,
    release_ledger_context,
    summarize_release_events,
)
from scripts import run_deepseek_release_batch as batch_runner
from scripts.run_deepseek_release_batch import _atomic_create_json, _atomic_replace_json
from scripts.run_deepseek_release_batch import _budget_exceeded, _budget_failure_category, _merge_ledger_metrics, _sync_process_ledger


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

    def test_final_after_failed_batch_uses_a_new_single_use_lock(self) -> None:
        """A repaired Runtime may consume one new final batch without reusing A."""

        with TemporaryDirectory() as directory:
            root = Path(directory)
            lock = root / "new-release-lock.json"
            report = root / "final.json"
            ledger_path = root / "ledger.jsonl"

            def sync(ledger: dict[str, object]) -> bool:
                ledger.update({"providerRequests": 1, "successfulRequests": 1, "failedRequests": 0, "totalTokens": 5, "ledgerReconciled": True})
                return True

            completed = {
                "status": "passed",
                "realLocalShowcase": {"status": "passed"},
                "main": {"status": "passed"},
                "supplemental": {"status": "passed"},
                "grounding": {"status": "passed"},
            }
            with patch.object(batch_runner, "settings", SimpleNamespace(deepseek_model="deepseek-flash", deepseek_api_key="fixture-only")), patch.object(
                batch_runner, "_runtime_identity", return_value=(True, "ok")
            ), patch.object(batch_runner, "_run_portfolio_b", return_value=completed), patch.object(
                batch_runner, "_sync_process_ledger", side_effect=sync
            ), patch.object(batch_runner, "verify_local_demo_accounts", return_value=SimpleNamespace(status="passed", account_count=2)), patch.dict(
                os.environ, {"MALL_LIVE_DEMO_PASSWORD": "only-for-offline-test-123"}, clear=False
            ), patch.object(
                sys, "argv", ["runner", "--phase", "portfolio_final", "--release-id", "new-release", "--runtime-commit", "a" * 40, "--report", str(report), "--lock", str(lock)]
            ), patch.dict(os.environ, {"MALL_RELEASE_LEDGER_PATH": str(ledger_path)}, clear=False):
                self.assertEqual(0, batch_runner.main())

            result_lock = json.loads(lock.read_text(encoding="utf-8"))
            self.assertEqual("PASSED", result_lock["status"])
            self.assertEqual(1, len(result_lock["batchIds"]))
            self.assertEqual("portfolio_final", result_lock["phase"])

    def test_report_zero_metrics_never_overwrite_shared_provider_ledger(self) -> None:
        ledger = {"requests": 12, "providerRequests": 12, "totalTokens": 80, "environmentBlocked": 0}
        _merge_ledger_metrics(ledger, [{"llm": {"total_calls": 0, "total_tokens": 0}, "toolCalls": 3}])
        self.assertEqual(12, ledger["requests"])
        self.assertEqual(12, ledger["providerRequests"])
        self.assertEqual(80, ledger["totalTokens"])
        self.assertEqual(3, ledger["toolCalls"])

    def test_budget_is_classified_before_next_phase_as_budget_exhausted(self) -> None:
        request_limited = {"providerHttpAttempts": 601, "totalTokens": 10}
        token_limited = {"providerHttpAttempts": 10, "totalTokens": 1_600_001}
        self.assertTrue(_budget_exceeded(request_limited))
        self.assertTrue(_budget_exceeded(token_limited))
        self.assertEqual("budget_exhausted", _budget_failure_category(request_limited))
        self.assertEqual("budget_exhausted", _budget_failure_category(token_limited))

    def test_reservation_allows_six_hundred_then_denies_before_network(self) -> None:
        with TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.jsonl"
            ledger.touch()
            budget = {
                "MALL_RELEASE_MAX_PROVIDER_HTTP_ATTEMPTS": "600",
                "MALL_RELEASE_MAX_TOTAL_TOKENS": "9000000",
                "MALL_RELEASE_RESERVE_TOKENS": "12000",
            }
            with patch.dict(os.environ, budget, clear=False), release_ledger_context(batch_id="budget-600", path=ledger):
                reservations = [reserve_provider_attempt() for _ in range(600)]
                self.assertTrue(all(reservations))
                with self.assertRaises(ReleaseLedgerBudgetError):
                    reserve_provider_attempt()
            summary = summarize_release_events(read_release_events(ledger, batch_id="budget-600"))
            self.assertEqual(600, summary["providerHttpAttempts"])
            self.assertEqual(0, summary["providerRequests"])
            self.assertEqual(1, summary["deniedBeforeNetwork"])

    def test_token_reservation_allows_equal_limit_and_denies_over_limit(self) -> None:
        with TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.jsonl"
            ledger.touch()
            budget = {
                "MALL_RELEASE_MAX_PROVIDER_HTTP_ATTEMPTS": "10",
                "MALL_RELEASE_MAX_TOTAL_TOKENS": "24000",
                "MALL_RELEASE_RESERVE_TOKENS": "12000",
            }
            with patch.dict(os.environ, budget, clear=False), release_ledger_context(batch_id="budget-token", path=ledger):
                first = reserve_provider_attempt()
                second = reserve_provider_attempt()
                with self.assertRaises(ReleaseLedgerBudgetError):
                    reserve_provider_attempt()
                settle_provider_attempt(first)
                settle_provider_attempt(second)

    def test_malformed_active_ledger_fails_closed(self) -> None:
        with TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.jsonl"
            ledger.write_text("not-json\n", encoding="utf-8")
            with patch.dict(os.environ, {"MALL_RELEASE_MAX_PROVIDER_HTTP_ATTEMPTS": "600"}, clear=False), release_ledger_context(batch_id="malformed", path=ledger):
                with self.assertRaises(ReleaseLedgerIntegrityError):
                    reserve_provider_attempt()

    def test_concurrent_reservations_never_exceed_shared_limit(self) -> None:
        with TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.jsonl"
            ledger.touch()
            budget = {
                "MALL_RELEASE_MAX_PROVIDER_HTTP_ATTEMPTS": "8",
                "MALL_RELEASE_MAX_TOTAL_TOKENS": "96000",
                "MALL_RELEASE_RESERVE_TOKENS": "12000",
            }

            def reserve_once(index: int) -> bool:
                with release_ledger_context(batch_id="concurrent", path=ledger, source=f"test{index}"):
                    try:
                        return reserve_provider_attempt() is not None
                    except ReleaseLedgerBudgetError:
                        return False

            with patch.dict(os.environ, budget, clear=False), ThreadPoolExecutor(max_workers=16) as pool:
                results = list(pool.map(reserve_once, range(16)))
            self.assertEqual(8, sum(results))
            summary = summarize_release_events(read_release_events(ledger, batch_id="concurrent"))
            self.assertEqual(8, summary["providerHttpAttempts"])

    def test_budget_denial_does_not_open_http_socket(self) -> None:
        with TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.jsonl"
            ledger.touch()
            budget = {
                "MALL_RELEASE_MAX_PROVIDER_HTTP_ATTEMPTS": "1",
                "MALL_RELEASE_MAX_TOTAL_TOKENS": "120000",
                "MALL_RELEASE_RESERVE_TOKENS": "12000",
            }
            fake_settings = SimpleNamespace(
                deepseek_api_key="fixture-only",
                deepseek_model="deepseek-flash",
                deepseek_base_url="http://127.0.0.1:1",
                deepseek_timeout_seconds=1.0,
            )
            with patch.dict(os.environ, budget, clear=False), patch("app.services.llm_service.settings", fake_settings), release_ledger_context(batch_id="denied", path=ledger), provider_access_context(
                mode="mock", release_id="fixture-release", batch_id="denied", ledger_path=str(ledger), runtime_commit="a" * 40, authorized=True, allow_mock=True
            ), patch("app.services.llm_service.httpx.post") as post:
                reserve_provider_attempt()
                with self.assertRaisesRegex(LLMServiceError, "budget exhausted") as caught:
                    generate_text("fixture input")
            self.assertEqual("budget_exhausted", caught.exception.category)
            post.assert_not_called()
            summary = summarize_release_events(read_release_events(ledger, batch_id="denied"))
            self.assertEqual(0, summary["providerRequests"])
            self.assertEqual(1, summary["deniedBeforeNetwork"])

    def test_each_retry_reserves_an_actual_http_attempt(self) -> None:
        with TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.jsonl"
            ledger.touch()
            budget = {
                "MALL_RELEASE_MAX_PROVIDER_HTTP_ATTEMPTS": "2",
                "MALL_RELEASE_MAX_TOTAL_TOKENS": "24000",
                "MALL_RELEASE_RESERVE_TOKENS": "12000",
            }
            fake_settings = SimpleNamespace(
                deepseek_api_key="fixture-only",
                deepseek_model="deepseek-flash",
                deepseek_base_url="http://127.0.0.1:1",
                deepseek_timeout_seconds=1.0,
            )
            response = httpx.Response(200, request=httpx.Request("POST", "http://127.0.0.1:1/v1/chat/completions"), json={"choices": [{"message": {"content": "synthetic answer"}}], "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}})
            with patch.dict(os.environ, budget, clear=False), patch("app.services.llm_service.settings", fake_settings), patch("app.services.llm_service.time.sleep"), release_ledger_context(batch_id="retry", path=ledger), provider_access_context(
                mode="mock", release_id="fixture-release", batch_id="retry", ledger_path=str(ledger), runtime_commit="a" * 40, authorized=True, allow_mock=True
            ), patch("app.services.llm_service.httpx.post", side_effect=[httpx.ConnectError("fixture"), response]) as post:
                self.assertEqual("synthetic answer", generate_text("fixture input"))
            self.assertEqual(2, post.call_count)
            summary = summarize_release_events(read_release_events(ledger, batch_id="retry"))
            self.assertEqual(2, summary["providerHttpAttempts"])
            self.assertEqual(1, summary["providerRequests"])


if __name__ == "__main__":
    unittest.main()
