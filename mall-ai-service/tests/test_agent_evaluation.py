import json
import unittest
from pathlib import Path

from app.services.agent_evaluation import evaluate_agent_cases, load_agent_evaluation_cases


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class AgentEvaluationTests(unittest.TestCase):
    def test_committed_cases_pass_with_the_real_agent_control_flow(self) -> None:
        cases = load_agent_evaluation_cases(PROJECT_ROOT / "evals" / "agent_cases.json")

        report = evaluate_agent_cases(cases)

        self.assertEqual(6, report["total_cases"])
        self.assertEqual(6, report["passed_cases"])
        self.assertEqual(0, report["failed_cases"])
        self.assertEqual(1.0, report["pass_rate"])
        self.assertEqual(1.0, report["process_check_summary"]["pass_rate"])
        self.assertEqual(1.0, report["result_check_summary"]["pass_rate"])

    def test_a_failed_expectation_is_reported_without_exposing_raw_message(self) -> None:
        secret_message = "请不要把这句测试原话写进评测报告"
        report = evaluate_agent_cases(
            [
                {
                    "id": "agent-mismatch",
                    "user_message": secret_message,
                    "model_responses": [{"content": "任意模型回答"}],
                    "tool_results": {},
                    "expected": {
                        "answer_contains": ["不存在的词"],
                        "max_steps": 1,
                    },
                }
            ]
        )

        case_report = report["cases"][0]
        self.assertFalse(case_report["passed"])
        self.assertFalse(case_report["result_checks"]["answer_contains"])
        self.assertNotIn(secret_message, json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
