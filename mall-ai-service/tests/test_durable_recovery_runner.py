import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_durable_recovery_local.py"
SPEC = importlib.util.spec_from_file_location("durable_recovery_runner_under_test", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_proposal_fixture_isolated_per_case_and_logs_in_via_public_api(tmp_path, monkeypatch):
    monkeypatch.setattr(MODULE, "ROOT", tmp_path)
    monkeypatch.setattr(MODULE, "SERVICE_ROOT", tmp_path / "mall-ai-service")
    login_calls = []

    def fake_run(command, *, cwd, env, text, capture_output, timeout, check):
        result_file = Path(env["MALL_LIVE_DEMO_RESULT_FILE"])
        result_file.parent.mkdir(parents=True, exist_ok=True)
        result_file.write_text(
            json.dumps({"account_a": {"username": "synthetic-isolated-user", "order_sn": "synthetic-isolated-order"}}),
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def fake_login(client, base, username, password):
        login_calls.append((client, base, username, password))
        return "Bearer synthetic"

    with patch.object(MODULE.subprocess, "run", side_effect=fake_run):
        monkeypatch.setattr(MODULE, "_login", fake_login)
        token, order = MODULE._prepare_proposal_fixture(object(), "http://example.test", "process-only", 7)

    assert token == "Bearer synthetic"
    assert order == "synthetic-isolated-order"
    assert login_calls[0][2:] == ("synthetic-isolated-user", "process-only")
    # The short-lived bootstrap result must be removed after the references
    # have been consumed; it is never part of a public report.
    assert not list((tmp_path / "tmp" / "durable-proposal-fixtures").glob("*.json"))


def test_store_recovery_waits_for_java_after_redis_container_is_healthy(monkeypatch):
    waits = []
    java_ready = []

    monkeypatch.setattr(
        MODULE,
        "_create_waiting_task",
        lambda *_args, **_kwargs: {"task_ref": "taskref-synthetic-recovery"},
    )
    monkeypatch.setattr(
        MODULE,
        "_compose",
        lambda _args: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    monkeypatch.setattr(
        MODULE,
        "_continue",
        lambda *_args, **_kwargs: {"task_ref": "taskref-synthetic-recovery"},
    )
    monkeypatch.setattr(
        MODULE,
        "_wait_healthy",
        lambda service: waits.append(service) or True,
    )
    monkeypatch.setattr(
        MODULE,
        "_wait_java_ready",
        lambda client, base: java_ready.append((client, base)) or True,
    )
    monkeypatch.setenv("MALL_JAVA_BASE_URL", "http://java.test:8085/")

    client = object()
    result = MODULE._run_store_recovery_case(
        client,
        "http://runtime.test",
        "Bearer synthetic",
        "synthetic-order",
    )

    assert waits == ["redis", "mall-portal"]
    assert java_ready == [(client, "http://java.test:8085")]
    assert "java_redis_dependency_recovered" in result["assertions"]
