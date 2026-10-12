"""校验当前迁移证据；离线通过不等于已部署或真实模型通过。"""
import hashlib
import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from handoff_upgrade_identity import ROOT, source_hash

REQUIRED_ENVIRONMENT_CHECKS = {
    "mongo_process_restart_resume", "mongo_crash_no_model_replay",
    "mongo_compare_and_swap", "mongo_memory_restart", "mongo_memory_delete",
    "mongo_memory_no_resurrection", "mongo_checkpoint_credentials_absent",
    "mongo_checkpoint_ttl", "redis_cross_process_lock",
    "java_timeout_original_request_reconciled", "java_no_duplicate_write",
    "legacy_confirmation_rejected", "policy_question", "single_query",
    "long_task", "multiple_task_selection", "task_interruption", "task_resume",
    "proposal_amend_cancel", "human_handoff", "operations_analysis",
    "browser_task_projection", "offline_provider_enforced",
}


def validate():
    facts = json.loads((ROOT / "docs/evidence/langgraph-migration-facts.json").read_text(encoding="utf-8"))
    assert facts["scope"] == "langgraph-unification-v1"
    assert facts["sourceSha256"] == source_hash(), "当前源码与迁移证据不一致"
    report_path = Path(os.getenv("MALL_FASTAPI_REPORT", str(ROOT / "mall-ai-service/ci-evidence/langgraph-fastapi-report.json")))
    if not report_path.is_absolute():
        report_path = ROOT / report_path
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["sourceSha256"] == facts["sourceSha256"] and report["sourceStable"]
    assert report["failures"] == report["errors"] == report["skipped"] == report["exitCode"] == 0
    assert report["passed"] == facts["pythonPassed"]
    junit_path = Path(os.getenv("MALL_FASTAPI_JUNIT", str(report_path.with_name("langgraph-fastapi-junit.xml"))))
    if not junit_path.is_absolute():
        junit_path = ROOT / junit_path
    assert hashlib.sha256(junit_path.read_bytes()).hexdigest() == report["junitSha256"]
    names = {case.attrib["name"] for case in ET.parse(junit_path).findall(".//testcase")
             if "test_graph_migration" in case.attrib.get("classname", "")}
    fixture = ROOT / "mall-ai-service/tests/test_graph_migration.py"
    assert facts["fixtureSha256"] == hashlib.sha256(fixture.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
    assert set(facts["migrationCaseIds"]) == names and names
    assert facts["historicalEvidenceRewritten"] is False
    if facts["status"] != "COMPLETE":
        assert facts["releaseComplete"] is False
    if facts["status"] in {"COMPLETE", "LOCAL_MIGRATION_VALIDATED"}:
        # 完成状态必须有独立实际环境报告，不能只依靠框架单测计数。
        path = ROOT / facts["environmentReport"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == facts["environmentReportSha256"]
        environment = json.loads(path.read_text(encoding="utf-8"))
        assert environment["sourceSha256"] == facts["sourceSha256"]
        assert environment["checks"] and all(check["passed"] for check in environment["checks"])
        check_ids = [check["caseId"] for check in environment["checks"]]
        assert len(check_ids) == len(set(check_ids)), "环境验收 caseId 重复"
        assert REQUIRED_ENVIRONMENT_CHECKS <= set(check_ids), "环境验收缺少必要能力"
        assert environment["externalProviderRequests"] == 0
        assert environment["storage"] == "real_mongo" and environment["java"] == "real_local"
        evidence_paths = set()
        for artifact in environment["artifacts"]:
            artifact_path = (ROOT / artifact["path"]).resolve()
            assert artifact_path.is_relative_to(ROOT.resolve())
            assert hashlib.sha256(artifact_path.read_bytes()).hexdigest() == artifact["sha256"]
            evidence_paths.add(artifact["path"])
        assert all(check["evidence"] in evidence_paths for check in environment["checks"])
        for runner, digest in environment["runnerHashes"].items():
            runner_path = (ROOT / runner).resolve()
            assert runner_path.is_relative_to(ROOT.resolve())
            assert hashlib.sha256(runner_path.read_bytes().replace(b'\r\n', b'\n')).hexdigest() == digest
    if facts.get("finalValidationReport"):
        final_path = ROOT / facts["finalValidationReport"]
        assert hashlib.sha256(final_path.read_bytes()).hexdigest() == facts["finalValidationReportSha256"]
        final = json.loads(final_path.read_text(encoding="utf-8"))
        assert final["sourceSha256"] == facts["sourceSha256"]
        assert final["runtimeCommit"] == facts["runtimeCommit"]
        assert final["liveConversationPassed"] == 9 and final["liveShowcasePassed"] == 1
        assert final["rollbackAssertionsPassed"] == 11 and final["ledgerReconciled"]
        assert final["usage"]["unresolvedReservations"] == final["usage"]["providerFailures"] == 0
        assert final["reservations"] == final["settlements"] == final["usage"]["providerHttpAttempts"]
        assert final["usage"]["providerHttpAttempts"] <= final["maxHttpAttempts"] == 80
        assert final["usage"]["totalTokens"] <= final["maxTokens"] == 200000
        for artifact in final["artifacts"]:
            artifact_path = (ROOT / artifact["path"]).resolve()
            assert artifact_path.is_relative_to(ROOT.resolve())
            assert hashlib.sha256(artifact_path.read_bytes()).hexdigest() == artifact["sha256"]
        for runner, digest in final["runnerHashes"].items():
            runner_path = (ROOT / runner).resolve()
            assert runner_path.is_relative_to(ROOT.resolve())
            assert hashlib.sha256(runner_path.read_bytes().replace(b'\r\n', b'\n')).hexdigest() == digest
    print("langgraph_migration_validation PASSED status="+facts["status"]+" source="+facts["sourceSha256"][:12])
    return 0


if __name__ == "__main__":
    raise SystemExit(validate())
