"""统一图迁移合同：合成数据、脚本 Provider，无网络/业务写入。"""
import hashlib
from types import SimpleNamespace
from unittest.mock import Mock
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.runtime.graph_checkpoint import TASK_GRAPH_VERSION, SafeSaver, task_saver, thread_config
from app.runtime.providers import ScriptedRuntimeProvider
from app.runtime.task_runtime import TaskRuntime, TaskRuntimeError
from app.runtime.task_store import InMemoryTaskStore, TaskStoreError, owner_ref_for_member
from app.schemas.agent_task import ExecutorDecision
from app.schemas.customer_service import CustomerServiceRequest, CustomerServiceResponse
from app.schemas.intent import IntentResponse
from app.services.conversation_memory import ConversationMemory
from app.services.conversation_state import reset_conversation_state_for_tests, get_conversation_manager
from app.services.conversation_entry import handle_unified_message
from app.services.tool_context import ToolExecutionContext
from app.skills.commerce_gateway import SyntheticSkillGateway

AUTH = "Bearer synthetic-graph-only"
MEMBER = 71


def ask():
    return ExecutorDecision(decision="ask_user", reason_summary="需要补充信息。", user_question="请说明需要查询的政策。")


def runtime(store=None, provider=None):
    return TaskRuntime(store=store or InMemoryTaskStore(), provider=provider or ScriptedRuntimeProvider(decisions=[ask(), ask()]),
                       gateway=SyntheticSkillGateway({}))


def create(r, goal="请查询售后政策"):
    return r.create_task(session_id="graph-fixture", goal=goal, member_id=MEMBER, authorization=AUTH).view


def test_checkpoint_restart_uses_same_wait_node_and_monotonic_budget():
    store = InMemoryTaskStore()
    first = runtime(store)
    task = create(first)
    config = thread_config(TASK_GRAPH_VERSION, owner_ref_for_member(MEMBER), task.task_ref)
    before = task_saver(store).get_tuple(config)
    assert before.checkpoint["channel_values"]["wait_type"] == "input"
    second = runtime(store)
    result = second.continue_task(task_ref=task.task_ref, message="继续查询政策", member_id=MEMBER, authorization=AUTH)
    assert result.view.task_ref == task.task_ref
    assert result.view.execution_metrics.model_calls == 2
    assert result.view.status == "waiting_for_user"


def test_crash_during_model_call_does_not_replay_on_recovery():
    class InterruptedProvider:
        def decide(self, context):
            raise RuntimeError("synthetic-private-crash-payload")
    store = InMemoryTaskStore()
    with pytest.raises(RuntimeError):
        create(runtime(store, InterruptedProvider()))
    task = next(iter(store._items.values())).task
    recovered = runtime(store)
    result = recovered.continue_task(task_ref=task.task_ref, message="继续", member_id=MEMBER, authorization=AUTH)
    assert result.view.status == "blocked"
    assert result.view.execution_metrics.model_calls == 1
    assert "interrupted_graph_run" in result.view.limitation_codes
    # 异常文本及凭证不能进入历史检查点或 pending writes。
    serialized = repr(list(task_saver(store).list(None)))
    assert "synthetic-private-crash-payload" not in serialized
    assert AUTH not in serialized
    next_result = recovered.continue_task(task_ref=task.task_ref, message="查询退货政策", member_id=MEMBER, authorization=AUTH)
    assert next_result.view.execution_metrics.model_calls == 2


def test_task_checkpoint_contains_no_request_credentials_or_identifiers():
    r = runtime()
    create(r, "查询政策，订单 123456789012，authorization=private-fixture")
    saved = repr(list(task_saver(r._store).list(None)))
    assert "123456789012" not in saved
    assert "private-fixture" not in saved
    assert AUTH not in saved
    assert "TaskGraph" not in saved or "task_ref" in saved


def test_stale_domain_writer_cannot_overwrite_latest_revision():
    r = runtime()
    task = create(r)
    left = r._store.load_owned(task.task_ref, owner_ref_for_member(MEMBER))
    right = r._store.load_owned(task.task_ref, owner_ref_for_member(MEMBER))
    r._store.save(left)
    with pytest.raises(TaskStoreError):
        r._store.save(right)


def test_display_status_is_rebuilt_from_same_revision_checkpoint():
    r = runtime()
    task = create(r)
    r._store._items[task.task_ref].task.status = "created"
    assert r.get_task(task_ref=task.task_ref, member_id=MEMBER, authorization=AUTH).status == "waiting_for_user"


def test_old_confirmation_is_not_forced_into_new_graph():
    r = runtime()
    task = create(r)
    r._store._items[task.task_ref].graph_version = None
    r._store._items[task.task_ref].graph_run_ref = None
    with pytest.raises(TaskRuntimeError, match="旧版本"):
        r.confirm_action(task_ref=task.task_ref, confirmation="confirm", member_id=MEMBER, authorization=AUTH)
    # 真正的旧执行器没有 TaskGraph 检查点，合成该迁移前状态。
    task_saver(r._store).delete_thread(thread_config(TASK_GRAPH_VERSION, owner_ref_for_member(MEMBER), task.task_ref)["configurable"]["thread_id"])
    resumed = r.continue_task(task_ref=task.task_ref, message="查询政策", member_id=MEMBER, authorization=AUTH)
    assert resumed.view.status == "waiting_for_user"
    assert r._store._items[task.task_ref].graph_version == TASK_GRAPH_VERSION


def test_incompatible_graph_version_blocks_without_model_call():
    r = runtime()
    task = create(r)
    r._store._items[task.task_ref].graph_version = "future-v99"
    with pytest.raises(TaskRuntimeError) as error:
        r.continue_task(task_ref=task.task_ref, message="继续", member_id=MEMBER, authorization=AUTH)
    assert error.value.code == "graph_version_mismatch"
    assert r._store._items[task.task_ref].task.model_calls == 1


def test_memory_retention_and_deletion_clear_all_checkpoint_versions():
    memory = ConversationMemory(saver=SafeSaver(InMemorySaver()))
    for _ in range(12):
        memory.append("synthetic-memory", "user", "退款材料不明确")
    assert len(memory.read("synthetic-memory")["fragments"]) == 8
    assert memory.read("synthetic-memory")["omitted"]
    memory.append("synthetic-memory", "user", "Bearer synthetic-secret")
    assert "synthetic-secret" not in repr(list(memory.saver.list(None)))
    memory.delete("synthetic-memory")
    assert memory.read("synthetic-memory")["deleted"]
    assert "退款" not in repr(list(memory.saver.list(None)))
    with pytest.raises(ValueError):
        memory.append("synthetic-memory", "user", "退款进度")


def test_late_turn_cannot_recreate_deleted_conversation_checkpoint():
    memory = ConversationMemory(saver=SafeSaver(InMemorySaver()))
    memory.delete("scope-a")
    config = {"metadata": {"session_ref": hashlib.sha256(b"scope-a").hexdigest()}}
    with pytest.raises(ValueError):
        memory.saver.put_writes(config, [("completed", True)], "task-test")


def test_conversation_request_dedup_and_scope(monkeypatch):
    from app.services import conversation_entry as entry
    reset_conversation_state_for_tests()
    fake = Mock()
    fake.list_tasks.return_value = []
    monkeypatch.setattr(entry, "get_task_runtime", lambda: fake)
    monkeypatch.setattr(entry, "choose_conversation_route", lambda *args: entry.ConversationRoute(route="clarify"))
    request = CustomerServiceRequest(session_id="scope-a", message="继续", unified_entry=True, request_id="request-unique")
    context = ToolExecutionContext(authorization=AUTH, member_id=MEMBER)
    handle_unified_message(request, context, public_session_id="public-a")
    memory_revision = get_conversation_manager().memory.read("scope-a")["revision"]
    again = handle_unified_message(request, context, public_session_id="public-a")
    assert "不会重复" in again.answer
    assert fake.list_tasks.call_count == 1
    assert get_conversation_manager().memory.read("scope-a")["revision"] == memory_revision
    handle_unified_message(request.model_copy(update={"session_id": "scope-b"}), context, public_session_id="public-b")
    assert fake.list_tasks.call_count == 2


def test_policy_interruption_does_not_continue_pending_task(monkeypatch):
    from app.services import conversation_entry as entry
    reset_conversation_state_for_tests()
    fake = Mock()
    fake.list_tasks.return_value = [SimpleNamespace(task_ref="taskref-a", status="waiting_for_user")]
    monkeypatch.setattr(entry, "get_task_runtime", lambda: fake)
    monkeypatch.setattr(entry, "choose_conversation_route", lambda *args: entry.ConversationRoute(route="answer"))
    monkeypatch.setattr(entry, "handle_customer_message", lambda request, context:
        CustomerServiceResponse(message=request.message, answer="合成政策回答", intent=IntentResponse(intent="unknown", route="chat", need_tool=False, source="system")))
    request = CustomerServiceRequest(session_id="scope-interrupt", message="咨询政策", unified_entry=True)
    result = handle_unified_message(request, ToolExecutionContext(authorization=AUTH, member_id=MEMBER), public_session_id="public-c")
    assert result.answer == "合成政策回答"
    fake.continue_task.assert_not_called()
    fake.create_task.assert_not_called()


def test_long_task_does_not_hold_conversation_lock(monkeypatch):
    from app.services import conversation_entry as entry
    reset_conversation_state_for_tests()
    started, release = Event(), Event()
    fake = Mock()
    fake.list_tasks.return_value = []
    def create_task(**kwargs):
        started.set()
        assert release.wait(4)
        raise TaskRuntimeError("合成停止")
    fake.create_task.side_effect = create_task
    monkeypatch.setattr(entry, "get_task_runtime", lambda: fake)
    monkeypatch.setattr(entry, "choose_conversation_route", lambda request, tasks:
        entry.ConversationRoute(route="start_task" if request.message == "调查" else "answer"))
    monkeypatch.setattr(entry, "handle_customer_message", lambda request, context:
        CustomerServiceResponse(message=request.message, answer="政策插问已回答", intent=IntentResponse(intent="unknown", route="chat", need_tool=False, source="system")))
    context = ToolExecutionContext(authorization=AUTH, member_id=MEMBER)
    request = CustomerServiceRequest(session_id="scope-parallel", message="调查", unified_entry=True, request_id="parallel-task")
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(handle_unified_message, request, context, public_session_id="public-parallel")
        assert started.wait(3)
        try:
            other = pool.submit(handle_unified_message, request.model_copy(update={"message": "政策", "request_id": "parallel-policy"}), context, public_session_id="public-parallel")
            assert other.result(timeout=3).answer == "政策插问已回答"
        finally:
            release.set()
        first.result(timeout=3)


def test_ambiguous_task_selection_never_guesses(monkeypatch):
    from app.services import conversation_entry as entry
    reset_conversation_state_for_tests()
    fake = Mock()
    fake.list_tasks.return_value = [SimpleNamespace(task_ref=f"taskref-{n}", status="waiting_for_user") for n in (1, 2)]
    monkeypatch.setattr(entry, "get_task_runtime", lambda: fake)
    monkeypatch.setattr(entry, "choose_conversation_route", lambda *args: entry.ConversationRoute(route="continue_task", task_ref="taskref-foreign"))
    result = handle_unified_message(CustomerServiceRequest(session_id="scope-multi", message="继续刚才的", unified_entry=True),
                                    ToolExecutionContext(authorization=AUTH, member_id=MEMBER), public_session_id="public-multi")
    assert "没有找到" in result.answer
    fake.continue_task.assert_not_called()
    fake.create_task.assert_not_called()


def test_java_timeout_reconciles_original_key_after_runtime_restart():
    from tests.test_task_runtime import _runtime, _decision, _observation, RecordingGateway
    from app.schemas.agent_task import SkillCall
    class LostReplyGateway(RecordingGateway):
        keys = []
        def commit(self, skill, arguments, **kwargs):
            self.commits.append((skill, arguments))
            raise TimeoutError("synthetic Java success but response lost")
        def reconcile(self, key, **kwargs):
            self.keys.append(key)
            return _observation(kind="action_result", reference="action-reconciled-fixture")
    gateway = LostReplyGateway({"read_order": _observation(reference="fact-order-migration")})
    provider = ScriptedRuntimeProvider(decisions=[
        _decision(name="call_skill", summary="核验订单。", calls=[SkillCall(skill_id="read_order", arguments={"orderRef": "ref-order-alpha"})]),
        _decision(name="propose_action", summary="等待确认。", action_skill="create_after_sales_draft",
                  action_arguments={"orderFactRef": "fact-order-migration", "applicationType": "return_refund"})])
    r = _runtime(provider, gateway)
    task = create(r, "核验订单后准备售后处理方案")
    unknown = r.confirm_action(task_ref=task.task_ref, confirmation="confirm", member_id=MEMBER, authorization=AUTH)
    assert unknown.view.action.confirmation_status == "unknown"
    restarted = TaskRuntime(store=r._store, provider=ScriptedRuntimeProvider(decisions=[]), gateway=gateway)
    reconciled = restarted.reconcile_handoff(task_ref=task.task_ref, member_id=MEMBER, authorization=AUTH)
    assert reconciled.view.status == "executing"
    assert len(gateway.commits) == 1
    assert gateway.keys == [gateway.commits[0][1]["idempotencyKey"]]
    with pytest.raises(TaskRuntimeError):
        restarted.confirm_action(task_ref=task.task_ref, confirmation="confirm", member_id=MEMBER, authorization=AUTH)
    assert len(gateway.commits) == 1


def test_expired_memory_does_not_reappear_as_old_context():
    memory = ConversationMemory(ttl=-1)
    memory.append("expired-fixture", "user", "退款材料不明确")
    assert memory.read("expired-fixture")["fragments"] == []


def test_capability_nodes_never_receive_credentials_as_langgraph_state(monkeypatch):
    from app.runtime.capability_graph import RequestLocalGraph
    from langgraph.graph import START, END
    from langgraph.pregel import Pregel
    original = Pregel.invoke
    observed = []
    def watch(self, input_value, *args, **kwargs):
        observed.append(input_value)
        return original(self, input_value, *args, **kwargs)
    monkeypatch.setattr(Pregel, "invoke", watch)
    builder = RequestLocalGraph(dict)
    builder.add_node("fixture", lambda payload: {"result": payload["authorization"] == AUTH})
    builder.add_edge(START, "fixture")
    builder.add_edge("fixture", END)
    assert builder.compile().invoke({"authorization": AUTH, "raw_message": "private-fixture"})["result"]
    assert observed == [{"sequence": 0}]


def test_second_request_cannot_advance_task_during_first_run():
    started, release = Event(), Event()
    class SlowProvider:
        def decide(self, context):
            started.set()
            assert release.wait(4)
            return ask()
    r = runtime(provider=SlowProvider())
    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(create, r)
        assert started.wait(3)
        task = next(iter(r._store._items.values())).task
        try:
            with pytest.raises(TaskRuntimeError) as error:
                r.continue_task(task_ref=task.task_ref, message="继续", member_id=MEMBER, authorization=AUTH)
            assert error.value.code == "task_busy"
        finally:
            release.set()
        running.result(timeout=3)
    assert r._store._items[task.task_ref].task.model_calls == 1


def test_domain_success_checkpoint_failure_rebuilds_without_replaying(monkeypatch):
    r = runtime()
    task = create(r)
    saver = task_saver(r._store)
    original = saver.put
    def failed_put(config, checkpoint, metadata, versions):
        if checkpoint["channel_values"].get("model_calls", 0) == 2:
            raise RuntimeError("synthetic checkpoint unavailable")
        return original(config, checkpoint, metadata, versions)
    monkeypatch.setattr(saver, "put", failed_put)
    with pytest.raises(RuntimeError):
        r.continue_task(task_ref=task.task_ref, message="继续查询政策", member_id=MEMBER, authorization=AUTH)
    assert r._store._items[task.task_ref].task.model_calls == 2
    monkeypatch.setattr(saver, "put", original)
    restarted = runtime(r._store)
    recovered = restarted.continue_task(task_ref=task.task_ref, message="核对结果", member_id=MEMBER, authorization=AUTH)
    assert recovered.view.execution_metrics.model_calls == 2
    assert recovered.view.status == "blocked"
