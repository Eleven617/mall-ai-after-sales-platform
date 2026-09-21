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
from scripts.run_deepseek_release_batch import (
    _budget_exceeded,
    _budget_failure_category,
    _load_minimal_retest_plan,
    _merge_ledger_metrics,
    _sync_process_ledger,
)


class _FakeProviderHandler(BaseHTTPRequestHandler):
    calls = 0
    failure_call: int | None = 4

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        type(self).calls += 1
        length = int(self.headers.get("content-length", "0"))
        self.rfile.read(length)
        if type(self).failure_call == type(self).calls:
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
    def test_minimal_retest_plan_is_single_run_and_strictly_bounded(self) -> None:
        plan = _load_minimal_retest_plan()
        self.assertEqual(1, plan["requiredRuns"])
        self.assertEqual(1, plan["maxAttemptsPerRequest"])
        self.assertEqual(11, plan["expectedEvaluationCases"])
        self.assertEqual(3, plan["expectedShowcaseChains"])
        self.assertEqual(80, plan["budget"]["maxProviderHttpAttempts"])
        self.assertEqual(200_000, plan["budget"]["maxTotalTokens"])
        self.assertEqual(80, plan["budgetPlan"]["plannedMaximumProviderHttpAttempts"])
        self.assertEqual(198_000, plan["budgetPlan"]["plannedMaximumTokens"])
        self.assertEqual(2_000, plan["budgetPlan"]["tokenHeadroom"])

    def test_minimal_retest_executes_only_reviewed_cases_once(self) -> None:
        agent_reports = [
            {"status": "passed", "failed": 0, "environmentBlocked": 0, "toolCalls": 2, "uniqueCases": 4, "requiredRunsPerCase": 1},
            {"status": "passed", "failed": 0, "environmentBlocked": 0, "toolCalls": 2, "uniqueCases": 3, "requiredRunsPerCase": 1},
        ]
        grounding_report = {
            "status": "passed",
            "quality_failed_cases": 0,
            "environment_blocked_cases": 0,
        }
        ledger: dict[str, object] = {"batchId": "minimal-fixture", "runtimeCommit": "a" * 40}
        with TemporaryDirectory() as directory, patch.object(
            batch_runner,
            "_run_portfolio_showcase",
            return_value={"status": "passed", "realLocalShowcase": {"status": "passed"}},
        ) as showcase_run, patch.object(
            batch_runner,
            "run_live_model_agent_evaluation",
            side_effect=agent_reports,
        ) as agent_run, patch.object(
            batch_runner,
            "load_rag2_golden_suite",
            return_value={"schema_version": "1", "suite_version": "fixture", "cases": [], "injection_fixtures": []},
        ), patch.object(
            batch_runner,
            "evaluate_grounded_answer_suite",
            return_value=grounding_report,
        ) as grounding_run, patch.object(
            batch_runner, "_sync_process_ledger", return_value=True
        ), patch.object(batch_runner, "_budget_exceeded", return_value=False):
            result = batch_runner._run_minimal_retest(ledger, Path(directory))

        self.assertEqual("passed", result["status"])
        self.assertEqual(2, agent_run.call_count)
        main_args = agent_run.call_args_list[0].kwargs
        supplemental_args = agent_run.call_args_list[1].kwargs
        self.assertEqual(
            {"agent-open-003", "agent-open-005", "agent-open-006", "agent-open-010"},
            main_args["case_ids"],
        )
        self.assertEqual(
            {"holdout-open-010", "holdout-open-011", "holdout-open-012"},
            supplemental_args["case_ids"],
        )
        self.assertEqual(1, main_args["required_runs"])
        self.assertEqual(1, supplemental_args["required_runs"])
        self.assertEqual(
            {"rag2-042", "rag2-043", "rag2-044", "rag2-045"},
            grounding_run.call_args.kwargs["case_ids"],
        )
        self.assertEqual(1, grounding_run.call_args.kwargs["max_attempts"])
        showcase_run.assert_called_once()
        self.assertEqual(
            ["main", "supplemental_v3", "grounding", "showcase"],
            result["retestPlan"]["executionOrder"],
        )

    def test_minimal_retest_quality_failure_skips_showcase_after_collecting_targets(self) -> None:
        agent_reports = [
            {"status": "quality_failed", "failed": 1, "environmentBlocked": 0, "toolCalls": 1, "uniqueCases": 4, "requiredRunsPerCase": 1},
            {"status": "passed", "failed": 0, "environmentBlocked": 0, "toolCalls": 1, "uniqueCases": 3, "requiredRunsPerCase": 1},
        ]
        grounding_report = {"status": "passed", "quality_failed_cases": 0, "environment_blocked_cases": 0}
        ledger: dict[str, object] = {"batchId": "minimal-quality", "runtimeCommit": "a" * 40}
        with TemporaryDirectory() as directory, patch.object(
            batch_runner, "_run_portfolio_showcase"
        ) as showcase_run, patch.object(
            batch_runner, "run_live_model_agent_evaluation", side_effect=agent_reports
        ) as agent_run, patch.object(
            batch_runner,
            "load_rag2_golden_suite",
            return_value={"schema_version": "1", "suite_version": "fixture", "cases": [], "injection_fixtures": []},
        ), patch.object(
            batch_runner, "evaluate_grounded_answer_suite", return_value=grounding_report
        ) as grounding_run, patch.object(
            batch_runner, "_sync_process_ledger", return_value=True
        ), patch.object(batch_runner, "_budget_exceeded", return_value=False):
            result = batch_runner._run_minimal_retest(ledger, Path(directory))

        self.assertEqual("failed", result["status"])
        self.assertEqual(2, agent_run.call_count)
        grounding_run.assert_called_once()
        showcase_run.assert_not_called()

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
        _FakeProviderHandler.failure_call = 4
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
                reservations = {
                    event["reservationId"]
                    for event in events
                    if event["eventType"] == "provider_reservation"
                }
                settlements = {
                    event["reservationId"]
                    for event in events
                    if event["eventType"] == "provider_reservation_settlement"
                }
                self.assertEqual(reservations, settlements)
                for event in events:
                    self.assertNotIn("prompt", event)
                    self.assertNotIn("messages", event)
                    self.assertNotIn("reasoning", event)
                    self.assertEqual("fake-batch", event["batchId"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_minimal_retest_entry_rehearses_order_and_shared_ledger_offline(self) -> None:
        _FakeProviderHandler.calls = 0
        _FakeProviderHandler.failure_call = None
        server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeProviderHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        stage_order: list[str] = []
        try:
            with TemporaryDirectory() as directory:
                root = Path(directory)
                ledger_path = root / "ledger.jsonl"
                ledger_path.touch()
                ledger: dict[str, object] = {
                    "batchId": "offline-minimal-rehearsal",
                    "runtimeCommit": "a" * 40,
                }
                fake_settings = SimpleNamespace(
                    deepseek_api_key="fixture-only",
                    deepseek_model="deepseek-flash",
                    deepseek_base_url=f"http://127.0.0.1:{server.server_port}",
                    deepseek_timeout_seconds=2.0,
                )

                def run_agent(*, case_ids: set[str], suite_path: Path, **_kwargs: object) -> dict[str, object]:
                    stage_order.append("main" if "agent-open-003" in case_ids else "supplemental_v3")
                    for case_id in sorted(case_ids):
                        self.assertEqual("synthetic answer", generate_text(f"fixture {case_id}"))
                    return {
                        "status": "passed",
                        "failed": 0,
                        "environmentBlocked": 0,
                        "toolCalls": len(case_ids),
                        "uniqueCases": len(case_ids),
                        "requiredRunsPerCase": 1,
                        "suitePath": str(suite_path),
                    }

                def run_grounding(_suite: object, *, case_ids: set[str], **_kwargs: object) -> dict[str, object]:
                    stage_order.append("grounding")
                    for case_id in sorted(case_ids):
                        self.assertEqual("synthetic answer", generate_text(f"fixture {case_id}"))
                    return {"status": "passed", "quality_failed_cases": 0, "environment_blocked_cases": 0}

                def run_showcase(_ledger: dict[str, object], _report_dir: Path) -> dict[str, object]:
                    stage_order.append("showcase")
                    for scenario in ("main", "pause_resume", "fact_change"):
                        self.assertEqual("synthetic answer", generate_text(f"fixture {scenario}"))
                    return {"status": "passed", "realLocalShowcase": {"status": "passed"}}

                budget_env = {
                    "MALL_RELEASE_LEDGER_PATH": str(ledger_path),
                    "MALL_RELEASE_MAX_PROVIDER_HTTP_ATTEMPTS": "80",
                    "MALL_RELEASE_MAX_TOTAL_TOKENS": "200000",
                    "MALL_RELEASE_RESERVE_TOKENS": "12000",
                    "MALL_RUNTIME_COMMIT": "a" * 40,
                }
                with patch.dict(os.environ, budget_env, clear=False), patch(
                    "app.services.llm_service.settings", fake_settings
                ), release_ledger_context(
                    batch_id="offline-minimal-rehearsal", path=ledger_path, source="offline_rehearsal"
                ), provider_access_context(
                    mode="mock",
                    release_id="offline-rehearsal",
                    batch_id="offline-minimal-rehearsal",
                    ledger_path=str(ledger_path),
                    runtime_commit="a" * 40,
                    authorized=True,
                    allow_mock=True,
                ), capture_llm_metrics(max_attempts=1, timeout_seconds=2.0), patch.object(
                    batch_runner, "run_live_model_agent_evaluation", side_effect=run_agent
                ), patch.object(
                    batch_runner,
                    "load_rag2_golden_suite",
                    return_value={"schema_version": "1", "suite_version": "fixture", "cases": [], "injection_fixtures": []},
                ), patch.object(
                    batch_runner, "evaluate_grounded_answer_suite", side_effect=run_grounding
                ), patch.object(batch_runner, "_run_portfolio_showcase", side_effect=run_showcase):
                    result = batch_runner._run_minimal_retest(ledger, root / "artifacts")

                events = read_release_events(ledger_path, batch_id="offline-minimal-rehearsal")
                summary = summarize_release_events(events)
                reservations = {
                    event["reservationId"]
                    for event in events
                    if event["eventType"] == "provider_reservation"
                }
                settlements = {
                    event["reservationId"]
                    for event in events
                    if event["eventType"] == "provider_reservation_settlement"
                }

                self.assertEqual("passed", result["status"])
                self.assertEqual(["main", "supplemental_v3", "grounding", "showcase"], stage_order)
                self.assertEqual(14, summary["providerRequests"])
                self.assertEqual(14, summary["providerHttpAttempts"])
                self.assertEqual(14, summary["providerSuccesses"])
                self.assertEqual(0, summary["providerFailures"])
                self.assertEqual(70, summary["totalTokens"])
                self.assertEqual(reservations, settlements)
                self.assertEqual(14, len(reservations))
                self.assertTrue(ledger["ledgerReconciled"])
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

    def test_provider_event_keeps_safe_scenario_and_runtime_role(self) -> None:
        with TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "release.jsonl"
            with release_ledger_context(
                batch_id="scenario-batch",
                path=ledger_path,
                source="fastapi",
                scenario="clarify_pause_resume",
            ):
                from app.services.release_ledger import append_release_event

                append_release_event(
                    event_type="provider_request",
                    operation="context_curator",
                    outcome="failed",
                    failure_class="network",
                )

            event = read_release_events(ledger_path, batch_id="scenario-batch")[0]
            self.assertEqual("clarify_pause_resume", event["scenario"])
            self.assertEqual("context_curator", event["operation"])
            self.assertNotIn("prompt", event)
            self.assertNotIn("reasoning", event)

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
