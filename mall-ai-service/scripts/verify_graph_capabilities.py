"""Container-only capability acceptance: real storage/Java, scripted model boundary."""
import json
import os
import sys
import uuid
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, '/app')


def run(data):
    assert os.environ.get('MALL_PROVIDER_LIVE_AUTH') == '0'
    checks = []
    def check(name, value):
        assert value, name
        checks.append({'caseId': name, 'passed': True})
    if data.get('mode') == 'operations':
        from app.services.operations_agent import analyze_case
        from app.services.operations_client import get_case_handoff
        from app.schemas.operations import OperationsAnalysisDraft
        case = get_case_handoff(data['case_ref'], data['authorization'])
        result = analyze_case(case=case, authorization=data['authorization'], generate_fn=lambda **kwargs:
            SimpleNamespace(value=OperationsAnalysisDraft(summary='合成验收：请人工复核聚合指标。', limitations=['脚本模型输出'])) )
        check('operations_analysis', result.metrics.window_days == 7 and result.draft.summary.startswith('合成验收'))
        return checks

    from app.config import settings
    from app.runtime.task_store import MongoTaskStore, owner_ref_for_member
    from app.runtime.task_runtime import TaskRuntime, TaskRuntimeError
    from app.runtime.providers import ScriptedRuntimeProvider
    from app.schemas.agent_task import ExecutorDecision
    from app.schemas.customer_service import CustomerServiceRequest
    from app.services.tool_context import ToolExecutionContext
    from app.services import conversation_entry as entry
    from app.services import rag_service
    from app.services.rag_evidence_verifier import verify_policy_evidence
    from app.services.conversation_state import get_conversation_manager
    from app.skills.unified_gateway import UnifiedSkillGateway
    auth = {'authorization': data['authorization'], 'member_id': data['member_id']}
    store = MongoTaskStore(settings.agent_task_mongo_url, data['database'], 'capability_tasks')
    ask = ExecutorDecision(decision='ask_user', reason_summary='请补充咨询内容。', user_question='请说明需要查询的政策。')
    runtime = TaskRuntime(store=store, provider=ScriptedRuntimeProvider(decisions=[ask]*5))
    session = 'graph-capability-'+uuid.uuid4().hex
    first = runtime.create_task(session_id=session, goal='查询退货政策', **auth).view
    second = runtime.create_task(session_id=session, goal='查询退款政策', **auth).view
    context = ToolExecutionContext(**auth)
    request = CustomerServiceRequest(session_id=session, message='刚才那个', unified_entry=True, request_id=uuid.uuid4().hex)
    with patch.object(entry, 'get_task_runtime', lambda: runtime), patch.object(entry, 'choose_conversation_route',
            lambda *args: entry.ConversationRoute(route='clarify')):
        result = entry.handle_unified_message(request, context, public_session_id=session)
        check('multiple_task_selection', result.agent_task is None and len(runtime.list_tasks(session_id=session, **auth)) == 2)
        revision = get_conversation_manager().memory.read(session)['revision']
        repeated = entry.handle_unified_message(request, context, public_session_id=session)
        check('conversation_request_dedup', '不会重复' in repeated.answer and get_conversation_manager().memory.read(session)['revision'] == revision)

    def evidence(question, chunks):
        selected = next((chunk for chunk in chunks if '七天' in chunk.section_path), chunks[0])
        return verify_policy_evidence(question, chunks, json_generator=lambda **kwargs:
            {'sufficient': True, 'supporting_chunk_ids': [selected.chunk_id]})
    def policy_answer(req, ctx):
        with patch.object(rag_service, 'verify_policy_evidence', evidence), patch.object(rag_service, 'generate_text',
                lambda **kwargs: '合成回答：七天无理由退货仍需符合商品状态要求。'):
            result = rag_service.answer_after_sales_question('七天无理由退货有什么条件？')
        check('policy_question', bool(result.sources) and not result.retrieval_unavailable and not result.no_evidence)
        return entry._reply(req, result.answer)
    with patch.object(entry, 'get_task_runtime', lambda: runtime), patch.object(entry, 'choose_conversation_route',
            lambda *args: entry.ConversationRoute(route='answer')), patch.object(entry, 'handle_customer_message', policy_answer):
        entry.handle_unified_message(request.model_copy(update={'message': '七天无理由退货有什么条件？', 'request_id': uuid.uuid4().hex}), context, public_session_id=session)
    check('task_interruption', runtime.get_task(task_ref=first.task_ref, **auth).execution_metrics.model_calls == 1)
    with patch.object(entry, 'get_task_runtime', lambda: runtime), patch.object(entry, 'choose_conversation_route',
            lambda *args: entry.ConversationRoute(route='continue_task', task_ref=first.task_ref)):
        resumed = entry.handle_unified_message(request.model_copy(update={'message': '继续查询政策', 'request_id': uuid.uuid4().hex}), context, public_session_id=session)
    check('task_resume', resumed.agent_task.task_ref == first.task_ref and resumed.agent_task.execution_metrics.model_calls == 2)
    check('unselected_task_unchanged', runtime.get_task(task_ref=second.task_ref, **auth).execution_metrics.model_calls == 1)

    from app.schemas.tool import ToolCall
    observation = UnifiedSkillGateway.invoke_tool(ToolCall(name='order_service', arguments={'order_sn': data['order_sn']}), context)
    check('single_query', observation is not None)
    # Only a newly-created synthetic record is marked legacy; no old data is changed.
    legacy = store.load_owned(second.task_ref, owner_ref_for_member(data['member_id']))
    legacy.graph_version = None
    store.save(legacy)
    try:
        runtime.confirm_action(task_ref=second.task_ref, confirmation='confirm', **auth)
        raise AssertionError('legacy_confirmation_accepted')
    except TaskRuntimeError as error:
        check('legacy_confirmation_rejected', error.code == 'legacy_graph_confirmation_disabled')
    return checks


if __name__ == '__main__':
    try:
        print(json.dumps({'checks': run(json.load(sys.stdin)), 'externalProviderRequests': 0,
                          'modelBoundary': 'scripted', 'storage': 'real_mongo', 'java': 'real_local'}))
    except Exception as error:
        import traceback
        print(json.dumps({'errorType': type(error).__name__, 'frames': [
            {'function': frame.name, 'line': frame.lineno, 'file': os.path.basename(frame.filename)}
            for frame in traceback.extract_tb(error.__traceback__)[-5:]]}))
        raise SystemExit(1)
