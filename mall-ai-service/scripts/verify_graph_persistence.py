"""Real Mongo/Redis acceptance. Run inside the offline AI container.

Uses a unique acceptance database, scripted decisions and synthetic identities.
Separate prepare/recover processes deliberately share only persisted references.
No external model, Java call, existing database mutation or database deletion.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import settings
from app.runtime.graph_checkpoint import TASK_GRAPH_VERSION, persistent_saver, thread_config
from app.runtime.providers import ScriptedRuntimeProvider
from app.runtime.task_runtime import TaskRuntime
from app.runtime.task_store import MongoTaskStore, TaskStoreError, owner_ref_for_member
from app.schemas.agent_task import ExecutorDecision
from app.services.conversation_memory import ConversationMemory
from app.services.reliability_service import reliability_governor, ConcurrentOperationError
from app.skills.commerce_gateway import SyntheticSkillGateway
from pymongo import MongoClient

MEMBER = 710071
AUTH = 'Bearer synthetic-persistence-acceptance'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', required=True)
    parser.add_argument('--phase', choices=['prepare', 'recover', 'locked'], required=True)
    args = parser.parse_args()
    assert args.database.startswith('mall_graph_acceptance_') and args.database.replace('_', '').isalnum()
    assert os.environ.get('MALL_RUNTIME_PROVIDER_MODE') in {'offline', 'deterministic'}
    assert os.environ.get('MALL_PROVIDER_LIVE_AUTH', '0') == '0'
    db = MongoClient(settings.agent_task_mongo_url)[args.database]
    store = MongoTaskStore(settings.agent_task_mongo_url, args.database, 'tasks')
    saver = persistent_saver(settings.agent_task_mongo_url, args.database)
    checks = []

    def check(name, result):
        assert result, name
        checks.append({'caseId': name, 'passed': True})

    def runtime(provider=None):
        decision = ExecutorDecision(decision='ask_user', reason_summary='需要补充信息。', user_question='请说明需要查询的政策。')
        return TaskRuntime(store=store, provider=provider or ScriptedRuntimeProvider(decisions=[decision]), gateway=SyntheticSkillGateway({}))

    if args.phase == 'locked':
        try:
            with reliability_governor.lock(scope=args.database, kind='session'):
                raise AssertionError('cross_process_lock_not_held')
        except ConcurrentOperationError:
            return 0

    memory = ConversationMemory(durable=True, saver=saver)
    if args.phase == 'prepare':
        task = runtime().create_task(session_id='persistence-fixture', goal='查询退货政策', member_id=MEMBER, authorization=AUTH).view
        db.receipts.insert_one({'kind': 'wait', 'task_ref': task.task_ref})
        check('mongo_wait_checkpoint', task.status == 'waiting_for_user')
        memory.append('synthetic-session', 'user', '查询退货政策')
        check('mongo_memory_saved', memory.read('synthetic-session')['revision'] == 1)
        class CrashedProvider:
            def decide(self, context):
                raise RuntimeError('synthetic-private-crash')
        try:
            runtime(CrashedProvider()).create_task(session_id='crash-fixture', goal='查询退货政策', member_id=MEMBER, authorization=AUTH)
        except RuntimeError:
            pass
        pending = [b for b in store.list_owned(owner_ref_for_member(MEMBER)) if b.graph_invocation_pending]
        check('mongo_crash_receipt', len(pending) == 1)
        db.receipts.insert_one({'kind': 'crash', 'task_ref': pending[0].task.task_ref})
    else:
        task_ref = db.receipts.find_one({'kind': 'wait'})['task_ref']
        result = runtime().continue_task(task_ref=task_ref, message='继续查询政策', member_id=MEMBER, authorization=AUTH)
        check('mongo_process_restart_resume', result.view.status == 'waiting_for_user' and result.view.execution_metrics.model_calls == 2)
        check('mongo_memory_restart', memory.read('synthetic-session')['revision'] == 1)
        left = store.load_owned(task_ref, owner_ref_for_member(MEMBER))
        right = store.load_owned(task_ref, owner_ref_for_member(MEMBER))
        store.save(left)
        try:
            store.save(right)
            raise AssertionError('stale_write_accepted')
        except TaskStoreError:
            check('mongo_compare_and_swap', True)
        crashed = db.receipts.find_one({'kind': 'crash'})['task_ref']
        result = runtime().continue_task(task_ref=crashed, message='继续', member_id=MEMBER, authorization=AUTH)
        check('mongo_crash_no_model_replay', result.view.status == 'blocked' and result.view.execution_metrics.model_calls == 1)
        saved = repr(list(saver.list(None)))
        check('mongo_checkpoint_credentials_absent', AUTH not in saved and 'synthetic-private-crash' not in saved)
        memory.delete('synthetic-session')
        check('mongo_memory_delete', memory.read('synthetic-session')['deleted'])
        second = ConversationMemory(durable=True, saver=persistent_saver(settings.agent_task_mongo_url, args.database))
        try:
            second.append('synthetic-session', 'user', '退货')
            raise AssertionError('deleted_memory_resurrected')
        except ValueError:
            check('mongo_memory_no_resurrection', True)
        indexes = db.orchestration_checkpoints_v1.index_information()
        check('mongo_checkpoint_ttl', any('expireAfterSeconds' in index for index in indexes.values()))
        import subprocess
        with reliability_governor.lock(scope=args.database, kind='session'):
            child = subprocess.run([sys.executable, __file__, '--database', args.database, '--phase', 'locked'], capture_output=True)
            check('redis_cross_process_lock', child.returncode == 0)
    report = {'phase': args.phase, 'checks': checks, 'externalProviderRequests': 0,
              'storage': 'real_mongo', 'locks': 'real_redis', 'time': time.time()}
    db.acceptance_reports.insert_one(dict(report))
    print(json.dumps(report))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
