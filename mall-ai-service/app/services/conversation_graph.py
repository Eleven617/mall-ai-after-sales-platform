"""会话入口图：路由与任务派发独立于长任务的检查点线程。"""
from __future__ import annotations

import hashlib
import uuid
import time
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from app.config import settings

from app.runtime.graph_checkpoint import CONVERSATION_GRAPH_VERSION, thread_config, invoke_graph
from app.runtime.task_runtime import TaskRuntimeError
from app.runtime.task_store import TaskStoreUnavailable
from app.services.conversation_state import get_conversation_manager
from app.services.llm_service import LLMServiceError
from app.services.structured_output_gateway import StructuredOutputError
from app.services.reliability_service import reliability_governor


class ConversationGraphState(TypedDict, total=False):
    graph_version: str
    request_digest: str
    route: str
    task_ref: str | None
    completed: bool
    expires_at: float


def run_conversation_graph(request, context, *, public_session_id, legacy_handler=None):
    from app.services import conversation_entry as entry
    runtime = entry.get_task_runtime() if context.member_id is not None else None
    active, response = [], None

    def receipt(answer):
        # 去重回执不再次写入会话记忆或推进任何事项。
        return entry.CustomerServiceResponse(message=request.message, answer=answer,
            intent=entry.IntentResponse(intent="unknown", route="chat", need_tool=False, source="system"))

    def route(state):
        nonlocal active
        if legacy_handler is not None:
            return {"route": "answer", "task_ref": None}
        tasks = runtime.list_tasks(session_id=public_session_id, member_id=context.member_id,
                                   authorization=context.authorization) if runtime else []
        active = [task for task in tasks if task.status not in {"completed", "cancelled"}]
        decision = entry.choose_conversation_route(request, active)
        # 模型引用先与当前成员会话的闭集相交，再进入任何检查点。
        selected = decision.task_ref if decision.task_ref in {task.task_ref for task in active} else None
        return {"route": decision.route, "task_ref": selected}

    def dispatch(state):
        nonlocal response
        decision = entry.ConversationRoute(route=state["route"], task_ref=state.get("task_ref"))
        if decision.route == "answer":
            # 传统领域工作流仍串行；TaskGraph 运行不占用该会话锁。
            with reliability_governor.lock(scope=request.session_id, kind="session", ttl_seconds=300):
                response = (legacy_handler(request, context) if legacy_handler is not None else
                            entry.dispatch_conversation_route(request, context, public_session_id, runtime, active, decision))
        else:
            response = entry.dispatch_conversation_route(request, context, public_session_id, runtime, active, decision)
        return {"completed": True}

    builder = StateGraph(ConversationGraphState)
    builder.add_node("route", route)
    builder.add_node("dispatch", dispatch)
    builder.add_edge(START, "route")
    builder.add_edge("route", "dispatch")
    builder.add_edge("dispatch", END)
    memory = get_conversation_manager().memory
    graph = builder.compile(checkpointer=memory.saver, name="ConversationGraph")
    request_id = request.request_id or uuid.uuid4().hex
    config = thread_config(CONVERSATION_GRAPH_VERSION, request.session_id, request_id)
    config["metadata"] = {"session_ref": hashlib.sha256(request.session_id.encode()).hexdigest()}
    digest = hashlib.sha256(request.message.encode()).hexdigest()
    try:
        with reliability_governor.lock(scope=config["configurable"]["thread_id"], kind="session", ttl_seconds=300):
            if memory.read(request.session_id).get("deleted"):
                raise ValueError("会话已删除")
            saved = graph.get_state(config)
            if saved.values and saved.values.get("expires_at", 0) <= time.time():
                memory.saver.delete_thread(config["configurable"]["thread_id"])
                saved = graph.get_state(config)
            if saved.values:
                if saved.values.get("request_digest") != digest:
                    return receipt("同一请求标识不能用于不同消息，请重新发送。")
                return receipt("该请求已接收，请刷新原事项查看结果；不会重复创建或推进任务。")
            invoke_graph(graph, {"graph_version": CONVERSATION_GRAPH_VERSION, "request_digest": digest,
                          "completed": False, "expires_at": time.time()+settings.conversation_ttl_seconds}, config)
        return response
    except (LLMServiceError, StructuredOutputError):
        return entry._reply(request, "智能客服暂时不可用，请稍后再试；没有提交业务操作。")
    except (TaskRuntimeError, TaskStoreUnavailable):
        return entry._reply(request, "当前事项暂时无法继续，请刷新处理详情后再试；没有通过对话提交业务操作。")
