"""HTTP contracts for the public Mall v3 Agent Task API."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import agent_tasks
from app.runtime.providers import ScriptedRuntimeProvider
from app.runtime.task_runtime import TaskRuntime, set_task_runtime_for_tests
from app.runtime.task_store import InMemoryTaskStore
from app.schemas.agent_task import ExecutorDecision
from app.schemas.authentication import MemberProfile
from app.skills.commerce_gateway import SyntheticSkillGateway


AUTHORIZATION = "Bearer synthetic-router-credential"


def _finish_runtime() -> TaskRuntime:
    return TaskRuntime(
        store=InMemoryTaskStore(),
        provider=ScriptedRuntimeProvider(
            decisions=[
                ExecutorDecision(
                    decision="finish",
                    reason_summary="合成任务已完成，未产生业务写入。",
                )
            ]
        ),
        gateway=SyntheticSkillGateway(observations={}),
    )


@pytest.fixture(autouse=True)
def runtime_reset():
    set_task_runtime_for_tests(None)
    yield
    set_task_runtime_for_tests(None)


def test_create_task_returns_only_safe_public_projection(monkeypatch) -> None:
    monkeypatch.setattr(
        agent_tasks,
        "get_current_member",
        lambda _authorization: MemberProfile(member_id=71, username="synthetic-customer"),
    )
    set_task_runtime_for_tests(_finish_runtime())
    client = TestClient(app)

    response = client.post(
        "/agent-tasks",
        headers={"Authorization": AUTHORIZATION},
        json={
            "session_id": "router-session",
            "goal": "核验合成订单 123456789012 后给出处理方案",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["goal"] == "核验合成订单 [业务标识] 后给出处理方案"
    serialized = json.dumps(payload, ensure_ascii=False)
    for forbidden in ("task_id", "owner_ref", "session_ref", "arguments_ref", "123456789012", "Bearer"):
        assert forbidden not in serialized


def test_other_member_receives_not_found_without_task_enumeration(monkeypatch) -> None:
    current_member = {"id": 71}
    monkeypatch.setattr(
        agent_tasks,
        "get_current_member",
        lambda _authorization: MemberProfile(member_id=current_member["id"], username="synthetic-customer"),
    )
    set_task_runtime_for_tests(_finish_runtime())
    client = TestClient(app)
    created = client.post(
        "/agent-tasks",
        headers={"Authorization": AUTHORIZATION},
        json={"session_id": "router-session", "goal": "完成合成任务"},
    )
    assert created.status_code == 201

    current_member["id"] = 72
    response = client.get(
        f"/agent-tasks/{created.json()['task_ref']}",
        headers={"Authorization": AUTHORIZATION},
    )

    assert response.status_code == 404
    assert "不属于当前用户" in response.json()["detail"]


def test_event_stream_is_safe_snapshot_without_internal_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        agent_tasks,
        "get_current_member",
        lambda _authorization: MemberProfile(member_id=71, username="synthetic-customer"),
    )
    set_task_runtime_for_tests(_finish_runtime())
    client = TestClient(app)
    created = client.post(
        "/agent-tasks",
        headers={"Authorization": AUTHORIZATION},
        json={"session_id": "router-session", "goal": "完成合成任务"},
    )

    response = client.get(
        f"/agent-tasks/{created.json()['task_ref']}/events/stream",
        headers={"Authorization": AUTHORIZATION},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "task_created" in response.text
    assert "owner_ref" not in response.text
    assert "arguments_ref" not in response.text
