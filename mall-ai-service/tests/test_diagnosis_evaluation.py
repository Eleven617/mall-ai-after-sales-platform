import unittest
from pathlib import Path

from app.services.diagnosis_evaluation import (
    evaluate_diagnosis_cases,
    load_diagnosis_cases,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DiagnosisEvaluationTests(unittest.TestCase):
    def test_committed_langgraph_cases_pass(self) -> None:
        cases = load_diagnosis_cases(PROJECT_ROOT / "evals" / "diagnosis_cases.json")
        report = evaluate_diagnosis_cases(cases)

        self.assertEqual(4, report["total_cases"])
        self.assertEqual(4, report["passed_cases"])
        self.assertEqual(0, report["failed_cases"])
        self.assertEqual(1.0, report["pass_rate"])


if __name__ == "__main__":
    unittest.main()
