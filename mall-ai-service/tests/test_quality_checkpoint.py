import json
import unittest

from app.services.llm_observability import (
    TokenPricing,
    capture_llm_metrics,
    record_llm_metric,
)
from app.services.llm_service import LLMServiceError
from app.services.quality_checkpoint import CheckpointBudget, run_quality_checkpoint


class QualityCheckpointTests(unittest.TestCase):
    def test_reports_progress_and_separates_quality_from_environment_failures(self) -> None:
        progress: list[dict[str, object]] = []

        def evaluate(case):
            if case["id"] == "network-case":
                raise LLMServiceError("do not expose this", category="network")
            if case["id"] == "quality-case":
                return {
                    "passed": False,
                    "checks": {"contract": False},
                    "user_message": "secret customer text must not be copied",
                }
            return {"passed": True, "checks": {"contract": True}}

        report = run_quality_checkpoint(
            checkpoint_name="test-checkpoint",
            cases=[
                {"id": "ok-case"},
                {"id": "network-case"},
                {"id": "quality-case"},
            ],
            evaluate_case=evaluate,
            budget=CheckpointBudget(max_cases=10, max_total_seconds=10),
            progress_listener=progress.append,
        )

        self.assertEqual("quality_failed", report["status"])
        self.assertEqual(
            {
                "passed": 1,
                "review_required": 0,
                "quality_failed": 1,
                "environment_blocked": 1,
                "budget_exhausted": 0,
            },
            report["case_status_counts"],
        )
        self.assertEqual(3, len(progress))
        self.assertEqual(3, report["progress"]["completed_cases"])
        encoded = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("secret customer text", encoded)
        self.assertEqual(["checks.contract"], report["cases"][2]["failed_checks"])

    def test_total_case_budget_marks_unrun_cases_without_running_them(self) -> None:
        calls: list[str] = []

        def evaluate(case):
            calls.append(case["id"])
            return {"passed": True}

        report = run_quality_checkpoint(
            checkpoint_name="budget-checkpoint",
            cases=[{"id": "first"}, {"id": "second"}],
            evaluate_case=evaluate,
            budget=CheckpointBudget(max_cases=1, max_total_seconds=10),
        )

        self.assertEqual(["first"], calls)
        self.assertEqual("budget_exhausted", report["status"])
        self.assertEqual(1, report["progress"]["not_run_cases"])
        self.assertEqual(1, len(report["cases"]))

    def test_review_signal_is_not_misreported_as_a_quality_or_network_failure(self) -> None:
        report = run_quality_checkpoint(
            checkpoint_name="retrieval-baseline",
            cases=[{"id": "unsupported-question"}],
            evaluate_case=lambda _case: {
                "passed": True,
                "checks": {"candidate_retrieval_completed": True},
                "review_checks": {"no_evidence_candidate_rejected": False},
            },
            budget=CheckpointBudget(max_cases=1, max_total_seconds=10),
        )

        self.assertEqual("review_required", report["status"])
        self.assertEqual(1, report["case_status_counts"]["review_required"])
        self.assertEqual(["review_checks.no_evidence_candidate_rejected"], report["cases"][0]["failed_checks"])

    def test_llm_metrics_are_opt_in_and_cost_is_only_estimated_with_usage(self) -> None:
        with capture_llm_metrics() as sink:
            record_llm_metric(
                operation="tools",
                outcome="succeeded",
                elapsed_ms=120,
                attempts=1,
                prompt_tokens=100,
                completion_tokens=40,
                total_tokens=140,
            )
            record_llm_metric(
                operation="json",
                outcome="failed",
                elapsed_ms=500,
                attempts=1,
                failure_class="timeout",
            )

        summary = sink.events
        self.assertEqual(2, len(summary))
        from app.services.llm_observability import summarize_llm_metrics

        aggregate = summarize_llm_metrics(
            summary,
            TokenPricing(input_per_million=1.0, output_per_million=2.0),
        )
        self.assertEqual(2, aggregate["total_calls"])
        self.assertIsNone(aggregate["estimated_cost"])
        self.assertEqual(["timeout"], aggregate["failure_classes"])


if __name__ == "__main__":
    unittest.main()
