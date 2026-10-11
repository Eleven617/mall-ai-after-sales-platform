"""Local synthetic acceptance through public HTTP; optional real model cases.

Only fixture identities are inserted by the isolated Docker bootstrap below.
Application code never connects to MySQL. Existing accounts are not changed.
"""
import concurrent.futures
import json
import os
import secrets
import subprocess
import sys
import time
import uuid
from pathlib import Path
import bcrypt
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bootstrap_live_demo import DemoAccount,_ensure_login
from app.services.release_ledger import summarize_release_events

ROOT=Path(__file__).resolve().parents[2]
BASE='http://127.0.0.1:5173/api'

def run():
    checks=[];fixture=uuid.uuid4().hex[:10];password=secrets.token_urlsafe(24)
    roles={'ops_'+fixture:'订单管理员','processor_'+fixture:'售后处理人员'}
    password_hash=bcrypt.hashpw(password.encode(),bcrypt.gensalt()).decode()
    sql='START TRANSACTION;'
    for username,role in roles.items():
        sql+=f"INSERT INTO ums_admin(username,password,nick_name,note,create_time,status) VALUES('{username}','{password_hash}','合成交接验收','isolated handoff fixture',NOW(),1);"
        sql+=f"INSERT INTO ums_admin_role_relation(admin_id,role_id) SELECT a.id,r.id FROM ums_admin a JOIN ums_role r ON r.name='{role}' WHERE a.username='{username}';"
    sql+='COMMIT;'
    result=subprocess.run(['docker','compose','exec','-T','mysql','sh','-c','MYSQL_PWD=$MYSQL_ROOT_PASSWORD;export MYSQL_PWD;exec mysql --user=root --default-character-set=utf8mb4 mall'],cwd=ROOT,input=sql,text=True,encoding='utf-8',capture_output=True)
    if result.returncode:raise RuntimeError('synthetic_identity_bootstrap_failed')
    ledger=ROOT/'tmp/local-chat-usage/ledger.jsonl'
    def events():return [json.loads(line) for line in ledger.read_text(encoding='utf-8').splitlines() if line]
    start=len(events())
    def check(name,ok):
        checks.append({'caseId':'handoff-v2-'+name,'passed':bool(ok)})
        print(json.dumps(checks[-1]),flush=True)
        if not ok:raise AssertionError(name)
    with httpx.Client(timeout=180,trust_env=False) as client:
        def call(method,path,auth=None,body=None,status=200):
            response=client.request(method,BASE+path,headers={'Authorization':auth} if auth else {},json=body)
            if response.status_code!=status:
                print(json.dumps({'endpoint':path.split('/')[1],'http':response.status_code,'expected':status}),flush=True)
                raise RuntimeError('http_assertion')
            return response.json()
        auth,_=_ensure_login(client,'http://127.0.0.1:8085',DemoAccount('handoff','handoff_'+fixture,password,'199'+str(uuid.uuid4().int%100000000).zfill(8)))
        auth2,_=_ensure_login(client,'http://127.0.0.1:8085',DemoAccount('isolation','other_'+fixture,password,'198'+str(uuid.uuid4().int%100000000).zfill(8)))
        ops=call('POST','/operations/auth/login',body={'username':'ops_'+fixture,'password':password})['authorization']
        processor=call('POST','/service-operations/auth/login',body={'username':'processor_'+fixture,'password':password})['authorization']
        session=str(uuid.uuid4());call('POST','/customer-service/conversations/'+session,auth)
        try:
            before=len(events())
            task=call('POST','/human-handoffs/prepare',auth,{'session_id':session,'topic':'policy','reason':'repeated_questions'})
            check('button_without_model',len(events())==before and task['status']=='ready_to_commit')
            changed=call('POST','/human-handoffs/prepare',auth,{'session_id':session,'topic':'policy','reason':'human_preference'})
            check('general_preview_revision',changed['task_ref']==task['task_ref'] and changed['action']['revision']==task['action']['revision']+1)
            task=call('POST','/human-handoffs/prepare',auth,{'session_id':session,'topic':'policy','reason':'repeated_questions'})
            check('no_case_before_confirmation',call('GET','/customer-service/service-cases',auth)==[])
            action=task['action'];ref=task['task_ref'];payload={'confirmation':'confirm','proposal_ref':action['proposal_ref'],'revision':action['revision']}
            committed=call('POST','/agent-tasks/'+ref+'/action',auth,payload)
            check('confirmed_waiting_human',committed['status']=='waiting_human')
            case=committed['handoff_case_ref']
            again=call('POST','/agent-tasks/'+ref+'/action',auth,payload)
            check('duplicate_confirmation_same_case',again['handoff_case_ref']==case and len(call('GET','/customer-service/service-cases',auth))==1)
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                responses=list(pool.map(lambda _:client.post(BASE+'/agent-tasks/'+ref+'/action',headers={'Authorization':auth},json=payload),range(2)))
            check('concurrent_confirmation_guard',all(response.status_code in {200,409} for response in responses) and len(call('GET','/customer-service/service-cases',auth))==1)
            call('POST','/agent-tasks/'+ref+'/messages',auth,{'message':'继续退款'},status=409)
            check('agent_write_frozen',True)
            call('GET','/agent-tasks/'+ref,auth2,status=404);check('cross_account_rejected',True)
            recovered=call('GET','/human-handoffs/'+ref+'/result',auth)
            check('original_request_lookup',recovered['handoff_case_ref']==case)
            owned=next(x for x in call('GET','/service-operations/cases',processor) if x['case_id']==case)
            claimed=call('POST','/service-operations/cases/'+case+'/claim',processor,{'expected_version':owned['state_version'],'idempotency_key':uuid.uuid4().hex})
            check('human_claim',claimed['state']=='CLAIMED' and claimed['assigned_to_me'])
            detail=call('GET','/handoff-management/processor/cases/'+case,processor)
            reviewed=call('POST','/handoff-management/processor/cases/'+case+'/review',processor,{'reason':'repeated_questions','version':detail['reviewVersion']})
            check('human_review_audited',reviewed['verifiedReason']=='repeated_questions' and len(reviewed['history'])>=1)
            call('POST','/handoff-management/processor/cases/'+case+'/review',ops,{'reason':'unspecified','version':1},status=403);check('operator_cannot_review_case',True)
            metrics=call('GET','/handoff-management?days=7&page=1&size=50&topic=policy',ops)
            check('window_contains_new_case',any(x['caseRef']==case for x in metrics['items']))
            check('same_filter_totals',sum(int(x['count']) for x in metrics['reasons'])==metrics['totals']['total'])
            metrics30=call('GET','/handoff-management?days=30&page=1&size=1&topic=policy&source=customer_requested&reason=repeated_questions',ops)
            check('thirty_day_pagination_consistent',len(metrics30['items'])==1 and sum(int(x['count']) for x in metrics30['reasons'])==metrics30['totals']['total'])
            check('structured_context_no_raw_text',detail.get('context',{}).get('completedSteps')==0 and 'taskRef' not in detail)
            improvement=call('POST','/handoff-management/improvements',ops,{'caseRef':case,'reason':'repeated_questions','team':'engineering'})['improvementRef']
            for version,state in enumerate(('TRIAGED','IN_PROGRESS','VERIFYING','CLOSED'),start=1):
                call('PATCH','/handoff-management/improvements/'+improvement,ops,{'state':state,'version':version,'verificationCode':'manual_verified' if state=='CLOSED' else 'not_verified'})
            check('improvement_verified_closure',any(x['improvementRef']==improvement and x['state']=='CLOSED' for x in call('GET','/handoff-management/improvements',ops)))
            for action_name,expected_state in [('start_review','IN_REVIEW'),('resolve','RESOLVED'),('close','CLOSED')]:
                claimed=call('POST','/service-operations/cases/'+case+'/actions',processor,{'action':action_name,'expected_version':claimed['state_version'],'idempotency_key':uuid.uuid4().hex,'public_message':'合成验收：已核实咨询并给出处理说明。'})
                check('processor_'+action_name,claimed['state']==expected_state)
            preview=call('POST','/handoff-management/retention?dryRun=true&days=90',ops)
            check('retention_dry_run',preview['dryRun'] is True)
            call('POST','/handoff-management/cases/'+case+'/retention-hold?held=true',ops)
            call('POST','/handoff-management/cases/'+case+'/retention-hold?held=false',ops)
            check('retention_hold_authorized',True)
            if '--live-model' in sys.argv:
                live_session=str(uuid.uuid4());call('POST','/customer-service/conversations/'+live_session,auth)
                answer=call('POST','/customer-service',auth,{'session_id':live_session,'unified_entry':True,'message':'转人工一般需要等多久？我只是问问，现在不用转。'})
                check('question_not_handoff',not answer.get('agent_task'))
                answer=call('POST','/customer-service',auth,{'session_id':live_session,'unified_entry':True,'message':'我想找人工咨询退货政策，请帮我转人工。'})
                check('natural_language_handoff_preview',answer.get('agent_task',{}).get('status')=='ready_to_commit')
                check('language_request_no_auto_case',len(call('GET','/customer-service/service-cases',auth))==1)
            # The real worker is asynchronous; polling consumes no model itself.
            deadline=time.time()+60
            while time.time()<deadline:
                detail=call('GET','/handoff-management/cases/'+case,ops)
                if detail['analysisState'] in {'SUCCEEDED','FAILED','UNAVAILABLE'}:break
                time.sleep(2)
            check('analysis_terminal_without_blocking_case',detail['analysisState'] in {'SUCCEEDED','FAILED','UNAVAILABLE'})
            if '--live-model' in sys.argv:
                check('real_analysis_succeeded',detail['analysisState']=='SUCCEEDED' and len(detail.get('analysisVersions',[]))>=1)
            if '--browser' in sys.argv:
                from field_browser_support import BrowserSession
                with BrowserSession(password=password,evidence_dir=ROOT/'tmp/handoff-upgrade-browser',customer_username='handoff_'+fixture) as browser:
                    browser.operations_username='ops_'+fixture;browser.service_username='processor_'+fixture
                    browser.open_customer_conversation(session,expected_markers=('已登记',))
                    check('browser_customer_handoff',browser.page.evaluate("document.body.innerText.includes('转人工')") is True)
                    browser.open_route('operations');browser.page.wait_for("document.body.innerText.includes('人工交接与问题改进')")
                    check('browser_operations',True)
                    browser.open_route('service_operations');browser.page.wait_for("document.body.innerText.includes('人工售后协同处理台')")
                    check('browser_processor',True)
            if '--restart' in sys.argv:
                restarted=subprocess.run(['docker','compose','restart','mall-ai-service'],cwd=ROOT,capture_output=True)
                if restarted.returncode:raise RuntimeError('restart_failed')
                deadline=time.time()+90
                while time.time()<deadline:
                    try:
                        if client.get('http://127.0.0.1:8000/health').status_code==200:break
                    except httpx.HTTPError:pass
                    time.sleep(2)
                recovered=call('GET','/human-handoffs/'+ref+'/result',auth)
                check('restart_original_case_reconciled',recovered['handoff_case_ref']==case)
                again=call('POST','/agent-tasks/'+ref+'/action',auth,payload)
                check('restart_no_duplicate_case',again['handoff_case_ref']==case and len(call('GET','/customer-service/service-cases',auth))==1)
        finally:
            report={'date':'2026-10-11','scope':'synthetic local HTTP / real model when enabled','checks':checks,'provider':summarize_release_events(events()[start:])}
            target=ROOT/'tmp'/('handoff-upgrade-'+fixture+'.json');target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({'report':str(target),'provider':report['provider']},ensure_ascii=False),flush=True)

if __name__=='__main__':
    try:run()
    except Exception as exc:print(json.dumps({'stopped':type(exc).__name__}),flush=True);sys.exit(1)
