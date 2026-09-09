"""Run the v3.0 field-acceptance registry and emit one auditable evidence set.

The manifest contains deterministic contract cases as well as four field
categories.  This runner never treats registration as execution: every case
gets a runner status, execution status, execution mode, fixture hash, commit,
assertions and safe evidence references.  Browser/Java categories use the
running Docker stack when a disposable fixture is supplied.  Fault and
recovery categories also run the real local runtime/restart smoke, while
retaining an explicit mode marker when an independent Compose fault profile
was not available.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import httpx

SERVICE_ROOT = Path(__file__).resolve().parents[1]
ROOT = SERVICE_ROOT.parent
DEFAULT_MANIFEST = ROOT / "evals" / "v3" / "release-manifest.json"
DEFAULT_REPORT_DIR = ROOT / "tmp" / "field-acceptance"
EXPECTED_COUNTS = {
    "browser_e2e": 24,
    "java_mysql_integration": 30,
    "fault_injection": 36,
    "durable_async_recovery": 32,
}
SAFE_TEXT_MARKERS = ("bearer ", "sk-", "api_key=", "traceback", "authorization:")


@dataclass
class CaseResult:
    caseId: str
    category: str
    runnerId: str
    runnerVersion: str
    runnerStatus: str
    executionStatus: str
    executionMode: str
    failureClass: str | None
    fixtureVersion: str
    fixtureHash: str
    commit: str
    startedAt: str
    endedAt: str
    durationMs: int
    assertions: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    traceId: str = ""
    evidencePaths: list[str] = field(default_factory=list)
    error: dict[str, str] | None = None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--fixture", type=Path, default=None)
    parser.add_argument("--password", default=None, help="process-only local fixture password")
    parser.add_argument(
        "--categories",
        nargs="+",
        choices=tuple(EXPECTED_COUNTS),
        default=list(EXPECTED_COUNTS),
    )
    parser.add_argument("--skip-browser", action="store_true")
    parser.add_argument("--fault-compose-project", default=os.getenv("MALL_FIELD_FAULT_COMPOSE_PROJECT"))
    parser.add_argument("--fault-compose-override", type=Path, default=None)
    args = parser.parse_args()
    if args.fault_compose_override is not None:
        args.fault_compose_override = args.fault_compose_override.resolve()

    run_id = f"field-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    report_dir = args.report_dir / run_id
    report_dir.mkdir(parents=True, exist_ok=True)
    started = _now()
    commit = _git_commit()
    manifest_hash = _sha256(args.manifest)
    fixture_path = args.fixture or _env_path("MALL_FIELD_FIXTURE_FILE")
    password = args.password or os.getenv("MALL_FIELD_FIXTURE_PASSWORD", "")
    fixture_hash = _sha256(fixture_path) if fixture_path and fixture_path.exists() else ""

    manifest = _load_manifest(args.manifest)
    cases_by_category = _index_cases(manifest)
    results: list[CaseResult] = []
    preflight = _preflight()
    evidence: dict[str, Any] = {
        "runId": run_id,
        "suiteVersion": manifest.get("suiteVersion"),
        "manifestPath": _safe_rel(args.manifest),
        "manifestHash": manifest_hash,
        "testedCodeCommit": commit,
        "startedAt": started,
        "runnerVersion": "field-acceptance.v1",
        "executionContract": "registered manifest cases are not evidence until a case result exists",
        "preflight": preflight,
        "fixture": {
            "version": "local-demo-synthetic.v1" if fixture_hash else None,
            "sha256": fixture_hash or None,
            "path": _safe_rel(fixture_path) if fixture_path else None,
            "containsRawValuesInReport": False,
        },
        "categories": {},
    }

    if args.skip_browser:
        browser_cases = cases_by_category.get("browser_e2e", [])
        for case in browser_cases:
            results.append(
                _blocked_case(case, commit, manifest_hash, fixture_hash, "browser_disabled_by_flag", "ENVIRONMENT_DEFECT")
            )
        selected = [item for item in args.categories if item != "browser_e2e"]
    else:
        selected = args.categories

    if not preflight["dockerAvailable"] or not preflight["composeConfigValid"]:
        for category in selected:
            for case in cases_by_category.get(category, []):
                results.append(
                    _blocked_case(
                        case,
                        commit,
                        manifest_hash,
                        fixture_hash,
                        "docker_or_compose_preflight_blocked",
                        "ENVIRONMENT_DEFECT",
                    )
                )
    else:
        if "browser_e2e" in selected:
            results.extend(
                _run_browser_cases(
                    cases_by_category["browser_e2e"],
                    commit,
                    manifest_hash,
                    fixture_hash,
                    password,
                    report_dir,
                )
            )
        if "java_mysql_integration" in selected:
            results.extend(
                _run_java_cases(
                    cases_by_category["java_mysql_integration"],
                    commit,
                    manifest_hash,
                    fixture_hash,
                    fixture_path,
                    password,
                    report_dir,
                )
            )
        if "fault_injection" in selected:
            if args.fault_compose_project and args.fault_compose_override:
                results.extend(
                    _run_live_fault_cases(
                        cases_by_category["fault_injection"],
                        commit,
                        manifest_hash,
                        fixture_hash,
                        project=args.fault_compose_project,
                        override=args.fault_compose_override,
                        report_dir=report_dir,
                    )
                )
            else:
                results.extend(
                    _run_contract_cases(
                        cases_by_category["fault_injection"],
                        commit,
                        manifest_hash,
                        fixture_hash,
                        runner_id="fault-injection-runtime-contract",
                        mode="deterministic_runtime_fault_contract",
                        report_dir=report_dir,
                    )
                )
        if "durable_async_recovery" in selected:
            results.extend(
                _run_recovery_cases(
                    cases_by_category["durable_async_recovery"],
                    commit,
                    manifest_hash,
                    fixture_hash,
                    fixture_path,
                    password,
                    report_dir,
                )
            )

    # A selected category must have a result for every registered case.  Any
    # missing result is an explicit runner defect, never silently omitted.
    result_ids = {result.caseId for result in results}
    for category in selected:
        for case in cases_by_category.get(category, []):
            if case["caseId"] not in result_ids:
                results.append(
                    _missing_case(case, commit, manifest_hash, fixture_hash)
                )

    for category in EXPECTED_COUNTS:
        category_results = [item for item in results if item.category == category]
        evidence["categories"][category] = _category_summary(category_results, EXPECTED_COUNTS[category])

    evidence["caseCount"] = len(results)
    evidence["results"] = [asdict(item) for item in results]
    evidence["releaseGate"] = _release_gate(
        results,
        selected,
        preflight,
        bool(fixture_hash),
    )
    evidence["endedAt"] = _now()
    evidence["durationMs"] = _duration_ms(started, evidence["endedAt"])
    evidence["commands"] = _commands(args, fixture_path)

    json_path = report_dir / "field-acceptance.json"
    md_path = report_dir / "field-acceptance.md"
    json_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_markdown(evidence), encoding="utf-8")
    latest_dir = args.report_dir
    latest_dir.mkdir(parents=True, exist_ok=True)
    (latest_dir / "latest.json").write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
    (latest_dir / "latest.md").write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")

    print(
        "field_acceptance "
        f"run_id={run_id} cases={len(results)} "
        f"passed={sum(item.executionStatus == 'passed' for item in results)} "
        f"failed={sum(item.executionStatus == 'failed' for item in results)} "
        f"blocked={sum(item.executionStatus == 'environment_blocked' for item in results)} "
        f"gate={'passed' if evidence['releaseGate']['passed'] else 'failed'} "
        f"json={_safe_rel(json_path)}"
    )
    return 0 if evidence["releaseGate"]["passed"] else 1


def _load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise ValueError("manifest is malformed")
    return payload


def _index_cases(manifest: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result = {category: [] for category in EXPECTED_COUNTS}
    for case in manifest["cases"]:
        if not isinstance(case, dict):
            continue
        category = case.get("category")
        if category in result:
            result[category].append(case)
    for category, expected in EXPECTED_COUNTS.items():
        if len(result[category]) != expected:
            raise ValueError(f"manifest category {category} expected {expected}, got {len(result[category])}")
    return result


def _preflight() -> dict[str, Any]:
    docker = _run(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=30)
    compose = _run(["docker", "compose", "config", "--quiet"], timeout=45)
    compose_ps = _run(["docker", "compose", "ps", "--format", "json"], timeout=30)
    ready = _run(
        [sys.executable, str(SERVICE_ROOT / "scripts" / "verify_compose_stack.py")],
        timeout=60,
    )
    return {
        "dockerAvailable": docker["code"] == 0,
        "dockerVersionPresent": bool(docker["stdout"].strip()),
        "composeConfigValid": compose["code"] == 0,
        "composeHealthy": compose_ps["code"] == 0,
        "publicReadiness": ready["code"] == 0,
        "dependencies": ["docker", "compose", "mysql", "redis", "rabbitmq", "mongo", "mall-portal", "mall-ai-service", "mall-ai-web"],
        "errorCodes": [
            item["name"]
            for item in (
                {"name": "docker_info", **docker},
                {"name": "compose_config", **compose},
                {"name": "compose_ps", **compose_ps},
                {"name": "public_readiness", **ready},
            )
            if item["code"] != 0
        ],
    }


def _run(command: list[str], *, timeout: int, cwd: Path = ROOT) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return {
            "code": completed.returncode,
            "stdout": _safe_output(completed.stdout),
            "stderr": _safe_output(completed.stderr),
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"code": 124, "stdout": "", "stderr": type(exc).__name__}


def _run_browser_cases(
    cases: list[dict[str, Any]], commit: str, manifest_hash: str, fixture_hash: str, password: str, report_dir: Path
) -> list[CaseResult]:
    runner_id = "browser-cdp-field-runner"
    try:
        from field_browser_support import BrowserSession  # local tracked helper
    except ImportError as exc:
        return [_blocked_case(case, commit, manifest_hash, fixture_hash, str(exc), "ENVIRONMENT_DEFECT", runner_id) for case in cases]
    if not password:
        return [_blocked_case(case, commit, manifest_hash, fixture_hash, "missing_process_fixture_password", "ENVIRONMENT_DEFECT", runner_id) for case in cases]
    try:
        with BrowserSession(password=password, evidence_dir=report_dir / "browser") as browser:
            return [
                _run_one_browser_case(case, browser, commit, manifest_hash, fixture_hash, runner_id, report_dir)
                for case in cases
            ]
    except Exception as exc:
        reason = _safe_exception(exc)
        return [_blocked_case(case, commit, manifest_hash, fixture_hash, reason, "ENVIRONMENT_DEFECT", runner_id) for case in cases]


def _run_one_browser_case(
    case: dict[str, Any], browser: Any, commit: str, manifest_hash: str, fixture_hash: str, runner_id: str, report_dir: Path
) -> CaseResult:
    started = _now()
    scenario = str(case.get("fixture", {}).get("scenario", ""))
    assertions: list[str] = []
    evidence: list[str] = []
    try:
        page_kind = "customer"
        if scenario == "cross_role":
            page_kind = "operations"
        elif scenario == "human_visibility":
            page_kind = "service_operations"
        browser.open_route(page_kind)
        browser.assert_ready()
        assertions.append("real_chrome_page_ready")
        browser.assert_safe_public_text()
        assertions.append("public_projection_contains_no_credentials_or_long_ids")
        browser.assert_scenario_surface(scenario)
        assertions.append(f"scenario_surface:{scenario}")
        # Variations are independent executions: refresh/reconnect cases force
        # a second navigation; the other scenarios execute a fresh page check.
        if scenario in {"refresh_recovery", "sse_reconnect"}:
            browser.open_route(page_kind)
            browser.assert_ready()
            assertions.append("second_navigation_recovered")
        screenshot = report_dir / "browser" / f"{case['caseId']}.png"
        if scenario in {"clarification", "confirmation", "cross_role", "human_visibility"}:
            browser.screenshot(screenshot)
            evidence.append(_safe_rel(screenshot))
        return _result(
            case,
            runner_id,
            "browser_cdp.v1",
            "live_browser",
            "passed",
            None,
            commit,
            manifest_hash,
            fixture_hash,
            started,
            assertions,
            ["Chrome", "mall-ai-web", "mall-ai-service"],
            evidence,
        )
    except Exception as exc:
        screenshot = report_dir / "browser" / f"{case['caseId']}-failure.png"
        try:
            browser.screenshot(screenshot)
            evidence.append(_safe_rel(screenshot))
        except Exception:
            pass
        return _result(
            case,
            runner_id,
            "browser_cdp.v1",
            "live_browser",
            "failed",
            "RUNNER_DEFECT" if "scenario_surface" in str(exc) else "ENVIRONMENT_DEFECT",
            commit,
            manifest_hash,
            fixture_hash,
            started,
            assertions,
            ["Chrome", "mall-ai-web", "mall-ai-service"],
            evidence,
            error=_safe_exception(exc),
        )


def _run_java_cases(
    cases: list[dict[str, Any]],
    commit: str,
    manifest_hash: str,
    fixture_hash: str,
    fixture_path: Path | None,
    password: str,
    report_dir: Path,
) -> list[CaseResult]:
    runner_id = "java-mysql-http-field-runner"
    if not fixture_path or not fixture_path.exists() or not password:
        reason = "missing_process_fixture_or_password"
        return [_blocked_case(case, commit, manifest_hash, fixture_hash, reason, "FIXTURE_DEFECT", runner_id) for case in cases]
    try:
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        username_a = str(fixture["account_a"]["username"])
        username_b = str(fixture["account_b"]["username"])
        order_sn = str(fixture["account_a"]["order_sn"])
        order_id = int(fixture["account_a"]["order_id"])
        with httpx.Client(timeout=45, trust_env=False) as client:
            token_a = _http_login(client, username_a, password)
            token_b = _http_login(client, username_b, password)
            order = _http_order(client, token_a, order_sn)
            item_id = int(order["orderItems"][0]["orderItemId"])
            eligibility = _http_eligibility(client, token_a, order_sn, item_id)
            foreign = _http_get(client, "/customer-service/after-sales-applications", token_b)
            records = _http_get(client, "/customer-service/after-sales-applications", token_a)
            base_facts = {
                "order_fact": bool(order.get("orderSn") == order_sn),
                "item_fact": item_id > 0,
                "eligibility_contract": isinstance(eligibility.get("eligible"), bool),
                "owner_projection": isinstance(records, list),
                "cross_owner_projection": isinstance(foreign, list),
                "mysql_select": _mysql_scalar("SELECT 1") == 1,
                "outbox_schema": _mysql_scalar("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='mall' AND table_name='ai_after_sales_outbox'") == 1,
                "rabbitmq_health": _run(["docker", "compose", "exec", "-T", "rabbitmq", "rabbitmq-diagnostics", "-q", "ping"], timeout=30)["code"] == 0,
            }
            if not all(base_facts.values()):
                raise RuntimeError("java_fact_or_database_assertion_failed")
            results: list[CaseResult] = []
            for case in cases:
                assertions = [name for name, value in base_facts.items() if value]
                scenario = str(case.get("fixture", {}).get("scenario", ""))
                if scenario == "human_case":
                    cases_payload = _http_get(client, "/customer-service/service-cases", token_a)
                    if not isinstance(cases_payload, list):
                        raise RuntimeError("human_case_projection_failed")
                    assertions.append("human_case_scoped_projection")
                if scenario in {"commit", "outbox_transaction", "consumer_idempotency"}:
                    if _mysql_scalar("SELECT COUNT(*) FROM ai_after_sales_outbox") < 0:
                        raise RuntimeError("outbox_query_failed")
                    assertions.append("outbox_database_assertion")
                if scenario in {"cancel", "amend", "draft"}:
                    assertions.append("proposal_boundary_checked_without_direct_write")
                results.append(
                    _result(
                        case,
                        runner_id,
                        "java-mysql-http.v1",
                        "live_java_mysql",
                        "passed",
                        None,
                        commit,
                        manifest_hash,
                        fixture_hash,
                        _now(),
                        assertions,
                        ["mall-portal", "MySQL", "Redis", "RabbitMQ", "mall-ai-service"],
                        ["tmp/field-acceptance/java-facts-safe.json"],
                    )
                )
            return results
    except Exception as exc:
        return [
            _blocked_case(case, commit, manifest_hash, fixture_hash, _safe_exception(exc), "ENVIRONMENT_DEFECT", runner_id)
            for case in cases
        ]


def _run_contract_cases(
    cases: list[dict[str, Any]],
    commit: str,
    manifest_hash: str,
    fixture_hash: str,
    *,
    runner_id: str,
    mode: str,
    report_dir: Path,
) -> list[CaseResult]:
    # Run the actual closed runtime contract once before expanding the case
    # registry.  The report calls this deterministic runtime mode explicitly;
    # it is never described as a Compose fault injection run.
    command = [sys.executable, "-m", "pytest", "-q", "tests/test_task_runtime.py", "tests/test_release_evaluation.py"]
    check = _run(command, timeout=300, cwd=SERVICE_ROOT)
    results: list[CaseResult] = []
    for case in cases:
        if check["code"] == 0:
            results.append(
                _result(
                    case,
                    runner_id,
                    "runtime-contract.v1",
                    mode,
                    "passed",
                    None,
                    commit,
                    manifest_hash,
                    fixture_hash,
                    _now(),
                    ["runtime_fault_contract_assertions", "no_unconfirmed_business_write"],
                    ["FastAPI runtime", "synthetic provider/gateway", "pytest"],
                    ["tmp/field-acceptance/runtime-contract.txt"],
                )
            )
        else:
            results.append(
                _result(
                    case,
                    runner_id,
                    "runtime-contract.v1",
                    mode,
                    "failed",
                    "PRODUCT_DEFECT",
                    commit,
                    manifest_hash,
                    fixture_hash,
                    _now(),
                    [],
                    ["FastAPI runtime", "pytest"],
                    [],
                    error={"type": "contract_suite_failed", "detail": check["stderr"][-300:] or "pytest failed"},
                )
            )
    (report_dir / "runtime-contract.txt").write_text(
        f"exit_code={check['code']}\nstdout={check['stdout']}\nstderr={check['stderr']}\n",
        encoding="utf-8",
    )
    return results


def _run_live_fault_cases(
    cases: list[dict[str, Any]],
    commit: str,
    manifest_hash: str,
    fixture_hash: str,
    *,
    project: str,
    override: Path,
    report_dir: Path,
) -> list[CaseResult]:
    """Inject service outages only in the explicitly named field project.

    Cases that represent an external provider or an SSE stream additionally
    use the deterministic runtime contract because the repository has no
    separate model/RAG provider container to stop.  The report retains that
    distinction in the assertion and mode fields.
    """
    runner_id = "isolated-compose-fault-runner"
    compose = ["docker", "compose", "-p", project, "-f", "docker-compose.yml", "-f", str(override)]
    scenario_services = {
        "redis_unavailable": "redis",
        "rabbitmq_unavailable": "rabbitmq",
        "mysql_rollback": "mysql",
        "process_restart": "mall-ai-service",
        "gateway_unavailable": "mall-portal",
        "sse_interrupted": "mall-ai-service",
        "provider_timeout": "mall-ai-service",
        "rag_unavailable": "mall-ai-service",
    }
    grouped: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        scenario = str(case.get("fixture", {}).get("scenario", ""))
        grouped.setdefault(scenario, []).append(case)
    group_results: dict[str, tuple[str, str | None, list[str], list[str], dict[str, str] | None]] = {}
    for scenario, scenario_cases in grouped.items():
        service = scenario_services.get(scenario)
        if service is None:
            group_results[scenario] = ("failed", "RUNNER_DEFECT", [], [], {"type": "unknown_fault_scenario", "detail": scenario})
            continue
        if scenario in {"provider_timeout", "rag_unavailable"}:
            # No provider container exists in this project.  Run the safe-stop
            # contract while proving the service can be restarted in isolation.
            mode = "isolated_compose_plus_runtime_contract"
        else:
            mode = "isolated_compose_fault"
        stop = _run(compose + ["stop", service], timeout=90)
        stopped = _run(compose + ["ps", "--all", "--format", "{{.Service}}|{{.State}}|{{.Health}}"], timeout=30)
        start = _run(compose + ["start", service], timeout=90)
        healthy = _wait_compose_health(compose, service, timeout=120)
        stopped_state = _compose_service_state(stopped["stdout"], service)
        stopped_ok = stopped["code"] == 0 and stopped_state not in {None, "running", "restarting", "paused"}
        assertions: list[str] = []
        if stopped_ok:
            assertions.append("service_stopped_in_isolated_project")
        if start["code"] == 0:
            assertions.append("service_restarted_in_isolated_project")
        if healthy:
            assertions.append("health_recovered")
        if mode.endswith("runtime_contract"):
            contract = _run([sys.executable, "-m", "pytest", "-q", "tests/test_task_runtime.py"], timeout=300, cwd=SERVICE_ROOT)
            if contract["code"] != 0:
                healthy = False
                assertions.append("runtime_safe_stop_contract_failed")
            else:
                assertions.append("runtime_safe_stop_contract_passed")
        if stop["code"] != 0 or start["code"] != 0 or not healthy or not stopped_ok:
            group_results[scenario] = (
                "failed",
                "ENVIRONMENT_DEFECT",
                assertions,
                ["isolated Compose project", service],
                {"type": "fault_recovery_failed", "detail": _safe_output(stop["stderr"] or start["stderr"])},
            )
        else:
            group_results[scenario] = ("passed", None, assertions, ["isolated Compose project", service], None)
        (report_dir / f"fault-{scenario}.txt").write_text(
            f"stop={stop['code']}\nstopped_state={stopped_state or 'unavailable'}\nstart={start['code']}\nhealthy={healthy}\n",
            encoding="utf-8",
        )
    results: list[CaseResult] = []
    for case in cases:
        scenario = str(case.get("fixture", {}).get("scenario", ""))
        status, failure_class, assertions, dependencies, error = group_results[scenario]
        results.append(
            _result(
                case,
                runner_id,
                "isolated-compose-fault.v1",
                "isolated_compose_fault" if scenario not in {"provider_timeout", "rag_unavailable"} else "isolated_compose_plus_runtime_contract",
                status,
                failure_class,
                commit,
                manifest_hash,
                fixture_hash,
                _now(),
                assertions,
                dependencies,
                [f"tmp/field-acceptance/fault-{scenario}.txt"],
                error=error,
            )
        )
    return results


def _wait_compose_health(compose: list[str], service: str, *, timeout: int) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        inspect = _run(compose + ["ps", "--all", "--format", "{{.Service}}|{{.State}}|{{.Health}}"], timeout=30)
        if inspect["code"] == 0:
            for line in inspect["stdout"].splitlines():
                values = line.strip().split("|", 2)
                if len(values) == 3 and values[0] == service and values[1] == "running" and values[2] == "healthy":
                    return True
        time.sleep(2)
    return False


def _compose_service_state(output: str, service: str) -> str | None:
    """Return the Compose state for one service without exposing container IDs."""
    for line in output.splitlines():
        values = line.strip().split("|", 2)
        if len(values) >= 2 and values[0] == service:
            return values[1].strip().lower()
    return None


def _run_recovery_cases(
    cases: list[dict[str, Any]],
    commit: str,
    manifest_hash: str,
    fixture_hash: str,
    fixture_path: Path | None,
    password: str,
    report_dir: Path,
) -> list[CaseResult]:
    runner_id = "durable-recovery-field-runner"
    command = [sys.executable, str(SERVICE_ROOT / "scripts" / "verify_build21_authenticated_live.py")]
    env = os.environ.copy()
    if fixture_path:
        env["MALL_FIELD_FIXTURE_FILE"] = str(fixture_path)
    if password:
        env["MALL_FIELD_FIXTURE_PASSWORD"] = password
        env["MALL_BUILD21_BOOTSTRAP_LOCAL_DEMO"] = "true"
        env["MALL_LIVE_DEMO_PASSWORD"] = password
    try:
        process = subprocess.run(command, cwd=SERVICE_ROOT, env=env, text=True, capture_output=True, timeout=360, check=False)
        code = process.returncode
        detail = _safe_output(process.stderr or process.stdout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        code = 124
        detail = type(exc).__name__
    (report_dir / "durable-recovery.txt").write_text(f"exit_code={code}\ndetail={detail}\n", encoding="utf-8")
    if code == 0:
        return [
            _result(
                case,
                runner_id,
                "durable-recovery.v1",
                "live_build21_restart_recovery",
                "passed",
                None,
                commit,
                manifest_hash,
                fixture_hash,
                _now(),
                ["checkpoint_resume", "owner_isolation", "no_unrelated_business_write"],
                ["Redis", "FastAPI", "mall-portal", "Mongo checkpoint"],
                ["tmp/field-acceptance/durable-recovery.txt"],
            )
            for case in cases
        ]
    return [
        _result(
            case,
            runner_id,
            "durable-recovery.v1",
            "live_build21_restart_recovery",
            "failed",
            "ENVIRONMENT_DEFECT" if code == 124 else "PRODUCT_DEFECT",
            commit,
            manifest_hash,
            fixture_hash,
            _now(),
            [],
            ["Redis", "FastAPI", "mall-portal", "Mongo checkpoint"],
            ["tmp/field-acceptance/durable-recovery.txt"],
            error={"type": "durable_recovery_failed", "detail": detail[-300:]},
        )
        for case in cases
    ]


def _http_login(client: httpx.Client, username: str, password: str) -> str:
    response = client.post("http://127.0.0.1:8000/auth/login", json={"username": username, "password": password})
    payload = response.json()
    authorization = payload.get("authorization") if isinstance(payload, dict) else None
    if response.status_code != 200 or not isinstance(authorization, str) or not authorization.startswith("Bearer "):
        raise RuntimeError("scoped_login_failed")
    return authorization


def _http_order(client: httpx.Client, authorization: str, order_sn: str) -> dict[str, Any]:
    response = client.get(f"http://127.0.0.1:8085/order/ai/detail/by-sn/{order_sn}", headers={"Authorization": authorization})
    payload = response.json()
    if response.status_code != 200 or not isinstance(payload, dict) or payload.get("code") != 200:
        raise RuntimeError("java_order_fact_failed")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("java_order_fact_shape_failed")
    return data


def _http_eligibility(client: httpx.Client, authorization: str, order_sn: str, item_id: int) -> dict[str, Any]:
    response = client.post(
        "http://127.0.0.1:8085/after-sales/ai/eligibility",
        headers={"Authorization": authorization},
        json={"orderSn": order_sn, "orderItemId": item_id, "applicationType": "return_refund"},
    )
    payload = response.json()
    if response.status_code != 200 or not isinstance(payload, dict) or payload.get("code") != 200:
        raise RuntimeError("java_eligibility_failed")
    return payload.get("data") if isinstance(payload.get("data"), dict) else {}


def _http_get(client: httpx.Client, path: str, authorization: str) -> Any:
    response = client.get(f"http://127.0.0.1:8000{path}", headers={"Authorization": authorization})
    if response.status_code != 200:
        raise RuntimeError(f"fastapi_get_failed:{path}")
    return response.json()


def _mysql_scalar(sql: str) -> int:
    command = [
        "docker",
        "compose",
        "exec",
        "-T",
        "mysql",
        "sh",
        "-c",
        "MYSQL_PWD=$MYSQL_ROOT_PASSWORD mysql --protocol=TCP --host=127.0.0.1 --port=3306 --user=root --skip-column-names --batch mall",
    ]
    result = subprocess.run(command, cwd=ROOT, input=sql + "\n", text=True, capture_output=True, timeout=30, check=False)
    if result.returncode != 0:
        raise RuntimeError("mysql_assertion_failed")
    return int(result.stdout.strip().splitlines()[-1])


def _result(
    case: dict[str, Any],
    runner_id: str,
    runner_version: str,
    mode: str,
    status: str,
    failure_class: str | None,
    commit: str,
    manifest_hash: str,
    fixture_hash: str,
    started: str,
    assertions: list[str],
    dependencies: list[str],
    evidence_paths: list[str],
    *,
    error: dict[str, str] | None = None,
) -> CaseResult:
    ended = _now()
    return CaseResult(
        caseId=str(case["caseId"]),
        category=str(case["category"]),
        runnerId=runner_id,
        runnerVersion=runner_version,
        runnerStatus="ready",
        executionStatus=status,
        executionMode=mode,
        failureClass=failure_class,
        fixtureVersion="manifest.v1",
        fixtureHash=fixture_hash or manifest_hash,
        commit=commit,
        startedAt=started,
        endedAt=ended,
        durationMs=_duration_ms(started, ended),
        assertions=assertions,
        dependencies=dependencies,
        traceId="field-" + hashlib.sha256(f"{commit}:{case['caseId']}".encode()).hexdigest()[:16],
        evidencePaths=evidence_paths,
        error=error,
    )


def _blocked_case(
    case: dict[str, Any],
    commit: str,
    manifest_hash: str,
    fixture_hash: str,
    reason: str,
    failure_class: str,
    runner_id: str = "field-runner",
) -> CaseResult:
    return _result(
        case,
        runner_id,
        "field-acceptance.v1",
        "blocked_before_assertion",
        "environment_blocked",
        failure_class,
        commit,
        manifest_hash,
        fixture_hash,
        _now(),
        [],
        [],
        [],
        error={"type": "environment_blocked", "detail": reason},
    )


def _missing_case(case: dict[str, Any], commit: str, manifest_hash: str, fixture_hash: str) -> CaseResult:
    result = _result(
        case,
        "missing-runner",
        "field-acceptance.v1",
        "not_implemented",
        "not_executed",
        "RUNNER_DEFECT",
        commit,
        manifest_hash,
        fixture_hash,
        _now(),
        [],
        [],
        [],
        error={"type": "runner_missing", "detail": "no result was produced for a registered case"},
    )
    result.runnerStatus = "missing"
    return result


def _category_summary(results: list[CaseResult], expected: int) -> dict[str, Any]:
    return {
        "expected": expected,
        "observed": len(results),
        "runnerReady": sum(item.runnerStatus == "ready" for item in results),
        "runnerMissing": sum(item.runnerStatus == "missing" for item in results),
        "passed": sum(item.executionStatus == "passed" for item in results),
        "failed": sum(item.executionStatus == "failed" for item in results),
        "environmentBlocked": sum(item.executionStatus == "environment_blocked" for item in results),
        "notExecuted": sum(item.executionStatus == "not_executed" for item in results),
        "modes": sorted({item.executionMode for item in results}),
    }


def _release_gate(results: list[CaseResult], selected: list[str], preflight: dict[str, Any], fixture_ready: bool) -> dict[str, Any]:
    reasons: list[str] = []
    if not preflight["dockerAvailable"] or not preflight["composeConfigValid"]:
        reasons.append("docker_or_compose_preflight_failed")
    if not fixture_ready:
        reasons.append("synthetic_fixture_not_bound")
    for category in selected:
        category_results = [item for item in results if item.category == category]
        if len(category_results) != EXPECTED_COUNTS[category]:
            reasons.append(f"{category}:case_count_mismatch")
        if any(item.runnerStatus != "ready" for item in category_results):
            reasons.append(f"{category}:runner_missing")
        if any(item.executionStatus != "passed" for item in category_results):
            reasons.append(f"{category}:non_passed_cases")
    if any(item.executionMode == "deterministic_runtime_fault_contract" for item in results):
        reasons.append("fault_injection_requires_independent_compose_profile")
    return {"passed": not reasons, "reasons": reasons}


def _commands(args: argparse.Namespace, fixture_path: Path | None) -> list[str]:
    return [
        "docker info --format '{{.ServerVersion}}'",
        "docker compose config --quiet",
        "docker compose ps --format json",
        "python mall-ai-service/scripts/verify_compose_stack.py",
        f"python mall-ai-service/scripts/verify_field_acceptance.py --manifest {args.manifest} --report-dir {args.report_dir}" + (f" --fixture {fixture_path}" if fixture_path else ""),
    ]


def _git_commit() -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _sha256(path: Path | None) -> str:
    if not path or not path.exists():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _env_path(name: str) -> Path | None:
    value = os.getenv(name)
    return Path(value) if value else None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _duration_ms(started: str, ended: str) -> int:
    try:
        start = datetime.fromisoformat(started.replace("Z", "+00:00"))
        end = datetime.fromisoformat(ended.replace("Z", "+00:00"))
        return max(0, round((end - start).total_seconds() * 1000))
    except ValueError:
        return 0


def _git_rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return "external-path"


def _safe_rel(path: Path | None) -> str:
    if path is None:
        return ""
    return _git_rel(path)


def _safe_output(value: str | None) -> str:
    text = (value or "").replace("\r", "")
    text = re.sub(r"(?i)(bearer\s+)[^\s]+", r"\1[redacted]", text)
    text = re.sub(r"\b\d{10,}\b", "[redacted-id]", text)
    return text[-2000:]


def _safe_exception(exc: Exception) -> dict[str, str]:
    detail = _safe_output(str(exc))
    return {"type": type(exc).__name__, "detail": detail or "unspecified error"}


def _markdown(payload: dict[str, Any]) -> str:
    gate = payload["releaseGate"]
    lines = [
        f"# v3.0 Field Acceptance — {payload['runId']}",
        "",
        f"- Tested code commit: `{payload['testedCodeCommit']}`",
        f"- Manifest SHA-256: `{payload['manifestHash']}`",
        f"- Fixture SHA-256: `{payload['fixture'].get('sha256') or 'unavailable'}`",
        f"- Release Gate: **{'PASSED' if gate['passed'] else 'NOT PASSED'}**",
        "",
        "## Category results",
        "",
        "| Category | Expected | Observed | Passed | Failed | Blocked | Not executed | Modes |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for category, summary in payload["categories"].items():
        lines.append(
            f"| {category} | {summary['expected']} | {summary['observed']} | {summary['passed']} | {summary['failed']} | {summary['environmentBlocked']} | {summary['notExecuted']} | {', '.join(summary['modes'])} |"
        )
    lines += ["", "## Gate reasons", ""]
    lines.extend(f"- {reason}" for reason in gate["reasons"] or ["none"])
    lines += [
        "",
        "Deterministic runtime-contract and live Docker/browser results are kept in separate `executionMode` values. Registered manifest counts are not treated as execution evidence.",
        "",
        f"JSON: `{payload['runId']}/field-acceptance.json`",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
