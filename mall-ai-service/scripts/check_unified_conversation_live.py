"""Bounded real-model smoke check. Synthetic identities stay in memory."""
import json
import os
import secrets
import sys
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bootstrap_live_demo import DemoAccount, _ensure_login, _prepare_account_order
from app.services.release_ledger import summarize_release_events


def main():
    ledger = Path(os.getenv('MALL_VALIDATION_LEDGER', str(Path(__file__).resolve().parents[2] / 'tmp/local-chat-usage/ledger.jsonl')))
    def events():
        return [json.loads(line) for line in ledger.read_text(encoding='utf-8').splitlines() if line]
    start = len(events())
    checks = []
    def check(name, condition):
        checks.append({'case': name, 'passed': bool(condition)})
        print(json.dumps(checks[-1]), flush=True)
        if not condition:
            raise AssertionError(name)
    with httpx.Client(timeout=290, trust_env=False) as client:
        base = 'http://127.0.0.1:5173/api'
        java = 'http://127.0.0.1:8085'
        account = DemoAccount('unified', 'unified_' + uuid.uuid4().hex[:10], secrets.token_urlsafe(24), '199' + str(uuid.uuid4().int % 100000000).zfill(8))
        order = _prepare_account_order(client, java, account, 26, required_stock=1)
        auth, _ = _ensure_login(client, java, account)
        headers = {'Authorization': auth}
        session = str(uuid.uuid4())
        def call(method, path, **kwargs):
            response = client.request(method, base + path, headers=headers, **kwargs)
            if response.status_code >= 400:
                print(json.dumps({'http_status': response.status_code, 'operation': method}), flush=True)
                raise RuntimeError('HTTP_' + str(response.status_code))
            return response.json()
        call('POST', '/customer-service/conversations/' + session)
        def chat(message):
            usage = summarize_release_events(events()[start:])
            if usage['providerHttpAttempts'] >= 30 or usage['totalTokens'] >= 80000:
                raise RuntimeError('small_regression_budget_stop')
            return call('POST', '/customer-service', json={'session_id': session, 'message': message, 'unified_entry': True})
        try:
            if '--withdrawal-only' in sys.argv:
                answer = chat('请核验订单' + order.order_sn + '的状态和取消退款资格，我不需要商品了。准备取消退款方案，先不要提交。')
                task = answer.get('agent_task') or {}
                check('direct_order_creates_proposal', task.get('status') == 'ready_to_commit' and bool(task.get('action')))
                action = task['action']
                withdrawn = call('POST', '/agent-tasks/' + task['task_ref'] + '/action', json={'confirmation': 'withdraw', 'proposal_ref': action['proposal_ref'], 'revision': action['revision']})
                check('explicit_card_withdrawal', withdrawn.get('action') is None and withdrawn['status'] == 'executing')
                audit = call('GET', '/agent-tasks/' + task['task_ref'] + '/events')
                check('withdrawal_no_commit_event', not any(item['event_type'] == 'action_committed' for item in audit))
                return
            answer = chat('你好')
            check('greeting_without_task', bool(answer.get('answer')) and not answer.get('agent_task') and call('GET', '/agent-tasks', params={'session_id': session}) == [])
            answer = chat('我想取消退款，请先查订单状态和售后资格，再比较适用的处理方案，准备好后让我确认。')
            task = answer.get('agent_task') or {}
            check('automatic_task_clarification', task.get('status') == 'waiting_for_user' and bool(task.get('open_question')))
            ref = task['task_ref']
            answer = chat('七天无理由退货一般有什么要求？这是单独的政策咨询。')
            check('policy_detour_preserves_task', not answer.get('agent_task') and len(call('GET', '/agent-tasks', params={'session_id': session})) == 1)
            answer = chat('继续刚才的取消退款事项，订单号是' + order.order_sn + '，我不需要这个商品了。请准备取消退款方案，但先不要提交。')
            task = answer.get('agent_task') or {}
            check('resume_same_task_proposal', task.get('task_ref') == ref and task.get('status') == 'ready_to_commit' and bool(task.get('action')))
            action = task['action']
            answer = chat('确认这个方案')
            current = call('GET', '/agent-tasks/' + ref)
            check('text_confirmation_does_not_commit', current['action']['confirmation_status'] == 'awaiting_confirmation' and current['action']['revision'] == action['revision'])
            other_session = str(uuid.uuid4())
            call('POST', '/customer-service/conversations/' + other_session)
            check('session_isolation', call('GET', '/agent-tasks', params={'session_id': other_session}) == [])
            check('refresh_restores_task', call('GET', '/agent-tasks', params={'session_id': session})[0]['task_ref'] == ref)
            second = DemoAccount('isolation', 'unified_' + uuid.uuid4().hex[:10], secrets.token_urlsafe(24), '198' + str(uuid.uuid4().int % 100000000).zfill(8))
            second_auth, _ = _ensure_login(client, java, second)
            forbidden = client.get(base + '/agent-tasks/' + ref, headers={'Authorization': second_auth})
            check('account_isolation', forbidden.status_code == 404)
            withdrawn = call('POST', '/agent-tasks/' + ref + '/action', json={'confirmation': 'withdraw', 'proposal_ref': action['proposal_ref'], 'revision': action['revision']})
            check('explicit_card_withdrawal', withdrawn.get('action') is None and withdrawn['status'] == 'executing')
        finally:
            report={'usage': summarize_release_events(events()[start:]), 'checks': checks}
            if os.getenv('MALL_VALIDATION_REPORT'):
                Path(os.environ['MALL_VALIDATION_REPORT']).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'stopped': type(exc).__name__}), flush=True)
        sys.exit(1)
