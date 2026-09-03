from app.services.task_orchestration_evaluation import run_task_orchestration_evaluation


def test_task_orchestration_contract_mock_suite_is_side_effect_free_and_green() -> None:
    report = run_task_orchestration_evaluation(mode="contract_mock")

    assert report.suite_version == "task-orchestration.v1"
    assert report.total == 11
    assert report.passed == 11
    assert report.failed == 0
    assert report.environment_blocked == 0
    assert all(case.status == "PASSED" for case in report.cases)
