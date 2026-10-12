"""Synthetic Java commit with a deliberately lost reply, then real AI restart.

Credentials travel only through child stdin and memory. Only safe assertions
and opaque task references leave the worker; model access is disabled.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import uuid

ROOT = Path('/app') if '--worker' in sys.argv else Path(__file__).resolve().parents[2]


def worker(phase):
    sys.path.insert(0, '/app')
    from app.runtime.task_runtime import TaskRuntime, TaskRuntimeError
    from app.runtime.task_store import MongoTaskStore
    from app.skills.unified_gateway import UnifiedSkillGateway
    from app.services.mall_client import list_my_after_sales_applications
    from app.config import settings
    assert os.environ.get('MALL_RUNTIME_PROVIDER_MODE') == 'deterministic'
    assert os.environ.get('MALL_PROVIDER_LIVE_AUTH') == '0'
    data = json.load(sys.stdin)
    store = MongoTaskStore(settings.agent_task_mongo_url, data['database'], 'tasks')
    class LostReplyGateway(UnifiedSkillGateway):
        def commit(self, *args, **kwargs):
            observation = super().commit(*args, **kwargs)
            assert observation.status == 'succeeded', 'java_commit_not_succeeded'
            raise TimeoutError('synthetic reply loss after Java success')
    runtime = TaskRuntime(store=store, gateway=LostReplyGateway() if phase == 'prepare' else UnifiedSkillGateway())
    auth = {'authorization': data['authorization'], 'member_id': data['member_id']}
    if phase == 'prepare':
        task = runtime.create_task(session_id=data['session'], goal=f"订单号：{data['order_sn']}，申请取消退款，完成售后闭环", **auth).view
        assert task.status == 'ready_to_commit', 'proposal_missing'
        result = runtime.confirm_action(task_ref=task.task_ref, confirmation='confirm', **auth).view
        assert result.action.confirmation_status == 'unknown', 'unknown_status_missing'
        assert len(list_my_after_sales_applications(data['authorization'])) == 1, 'java_write_missing'
        print(json.dumps({'task_ref': task.task_ref, 'java_committed_reply_lost': True}))
    else:
        result = runtime.reconcile_handoff(task_ref=data['task_ref'], **auth).view
        assert result.status == 'executing', 'original_result_missing'
        try:
            runtime.confirm_action(task_ref=data['task_ref'], confirmation='confirm', **auth)
            raise AssertionError('duplicate_confirmation_accepted')
        except TaskRuntimeError:
            pass
        assert len(list_my_after_sales_applications(data['authorization'])) == 1, 'duplicate_java_write'
        print(json.dumps({'checks': [
            {'caseId': 'java_timeout_original_request_reconciled', 'passed': True},
            {'caseId': 'java_no_duplicate_write', 'passed': True}], 'externalProviderRequests': 0}))


def main():
    import httpx
    from bootstrap_live_demo import DemoAccount, _ensure_login, _prepare_account_order
    nonce = uuid.uuid4().hex[:12]
    account = DemoAccount('graph-recovery', 'graph_'+nonce, secrets.token_urlsafe(24), '195'+str(uuid.uuid4().int % 100000000).zfill(8))
    with httpx.Client(timeout=45, trust_env=False) as client:
        order = _prepare_account_order(client, 'http://127.0.0.1:8085', account, 26, required_stock=1)
        authorization, member = _ensure_login(client, 'http://127.0.0.1:8085', account)
        payload = {'authorization': authorization, 'member_id': member, 'order_sn': order.order_sn,
                   'database': 'mall_graph_acceptance_'+nonce, 'session': str(uuid.uuid4())}
        copied = subprocess.run(['docker', 'compose', 'cp', str(Path(__file__).resolve()),
                                 'mall-ai-service:/app/verify_graph_java_recovery.py'], cwd=ROOT, capture_output=True)
        assert copied.returncode == 0, 'worker_copy_failed'
        def invoke(phase):
            result = subprocess.run(['docker', 'compose', 'exec', '-T', 'mall-ai-service', 'python',
                '/app/verify_graph_java_recovery.py', '--worker', phase], cwd=ROOT,
                input=json.dumps(payload), capture_output=True, text=True, encoding='utf-8', timeout=120)
            if result.returncode:
                # No raw exception/HTTP payload can leak credentials into reports.
                diagnostic = json.loads(result.stdout) if result.stdout.strip().startswith('{') else {}
                print(json.dumps({'phase': phase, 'diagnostic': diagnostic}))
                raise RuntimeError('java_recovery_worker_'+phase+'_failed')
            return json.loads(result.stdout)
        first = invoke('prepare')
        payload['task_ref'] = first['task_ref']
        restarted = subprocess.run(['docker', 'compose', 'restart', 'mall-ai-service'], cwd=ROOT, capture_output=True)
        assert restarted.returncode == 0, 'restart_failed'
        deadline = time.monotonic()+90
        while time.monotonic() < deadline:
            try:
                if client.get('http://127.0.0.1:8000/health/ready').status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)
        else:
            raise RuntimeError('restart_health_timeout')
        report = invoke('recover')
        report.update({'java': 'real_local', 'storage': 'real_mongo', 'aiContainerRestarted': True,
                       'fault': 'raise_timeout_after_real_java_success'})
        target = ROOT/'tmp/langgraph-java-recovery.json'
        target.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(report))
        copied = subprocess.run(['docker', 'compose', 'cp', str(Path(__file__).with_name('verify_graph_capabilities.py')),
                                 'mall-ai-service:/app/verify_graph_capabilities.py'], cwd=ROOT, capture_output=True)
        assert copied.returncode == 0
        features = subprocess.run(['docker', 'compose', 'exec', '-T', 'mall-ai-service', 'python',
            '/app/verify_graph_capabilities.py'], cwd=ROOT, input=json.dumps(payload),
            capture_output=True, text=True, encoding='utf-8', timeout=180)
        result = json.loads(features.stdout)
        print(json.dumps(result))
        assert features.returncode == 0, 'capability_acceptance_failed'
        (ROOT/'tmp/langgraph-capabilities.json').write_text(json.dumps(result,indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    if '--worker' in sys.argv:
        try:
            worker(sys.argv[-1])
        except Exception as error:
            import traceback
            print(json.dumps({'errorType': type(error).__name__, 'frames': [
                {'function': frame.name, 'line': frame.lineno, 'file': Path(frame.filename).name}
                for frame in traceback.extract_tb(error.__traceback__)[-6:]]}))
            raise SystemExit(1)
    else:
        main()
