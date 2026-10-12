"""Synthetic HTTP/browser acceptance; summaries and group analysis use DeepSeek.

Bootstrap SQL is limited to new synthetic staff identities, not application DB access.
No credentials, customer input, raw prompts or model traces enter the report.
"""
import json, secrets, subprocess, sys, time, uuid
from pathlib import Path
import bcrypt
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bootstrap_live_demo import DemoAccount,_ensure_login
from app.services.release_ledger import summarize_release_events
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from handoff_upgrade_identity import source_hash
BASE='http://127.0.0.1:5173/api'

def run():
    fixture=uuid.uuid4().hex[:10];password=secrets.token_urlsafe(24);checks=[]
    group_title='换货材料说明待改进'+''.join(chr(ord('a')+int(x,16)) for x in fixture)
    ledger=ROOT/'tmp/local-chat-usage/ledger.jsonl'
    def events():return [json.loads(x) for x in ledger.read_text(encoding='utf-8').splitlines() if x]
    start=len(events())
    def check(name,ok):
        checks.append({'caseId':'semantic-'+name,'passed':bool(ok)});print(json.dumps(checks[-1]),flush=True)
        if not ok:raise AssertionError(name)
    hashed=bcrypt.hashpw(password.encode(),bcrypt.gensalt()).decode()
    sql='START TRANSACTION;'
    for role,prefix in [('订单管理员','sops_'),('售后处理人员','sprocessor_')]:
        username=prefix+fixture
        sql+=f"INSERT INTO ums_admin(username,password,nick_name,note,create_time,status) VALUES('{username}','{hashed}','合成语义验收','semantic synthetic fixture',NOW(),1);"
        sql+=f"INSERT INTO ums_admin_role_relation(admin_id,role_id) SELECT a.id,r.id FROM ums_admin a JOIN ums_role r ON r.name='{role}' WHERE a.username='{username}';"
    sql+='COMMIT;'
    result=subprocess.run(['docker','compose','exec','-T','mysql','sh','-c','MYSQL_PWD=$MYSQL_ROOT_PASSWORD;export MYSQL_PWD;exec mysql --user=root --default-character-set=utf8mb4 mall'],cwd=ROOT,input=sql,text=True,encoding='utf-8',capture_output=True)
    if result.returncode:raise RuntimeError('fixture_bootstrap_failed')
    try:
        with httpx.Client(timeout=60,trust_env=False) as client:
            def call(method,path,auth=None,body=None,status=200):
                r=client.request(method,BASE+path,headers={'Authorization':auth} if auth else {},json=body)
                if r.status_code!=status:
                    print(json.dumps({'route':path.split('?')[0],'http':r.status_code,'expected':status}),flush=True)
                    raise RuntimeError('http_assertion')
                return r.json()
            auth,_=_ensure_login(client,'http://127.0.0.1:8085',DemoAccount('semantic','semantic_'+fixture,password,'197'+str(uuid.uuid4().int%100000000).zfill(8)))
            ops=call('POST','/operations/auth/login',body={'username':'sops_'+fixture,'password':password})['authorization']
            processor=call('POST','/service-operations/auth/login',body={'username':'sprocessor_'+fixture,'password':password})['authorization']
            refs=[];sessions=[]
            for index,description in enumerate(['没有开箱视频还能申请换货吗','没有开箱录像是否可以申请换货','换货应该寄到哪里','转人工','电话19900000000，材料不明白']):
                session=str(uuid.uuid4());sessions.append(session);call('POST','/customer-service/conversations/'+session,auth)
                preview=call('POST','/human-handoffs/prepare',auth,{'session_id':session,'topic':'exchange','problem_description':description})
                check('preview-'+str(index),preview['status']=='ready_to_commit' and '19900000000' not in json.dumps(preview))
                action=preview['action'];payload={'confirmation':'confirm','proposal_ref':action['proposal_ref'],'revision':action['revision']}
                committed=call('POST','/agent-tasks/'+preview['task_ref']+'/action',auth,payload);refs.append(committed['handoff_case_ref'])
                check('confirm-'+str(index),committed['status']=='waiting_human')
                if index==0:
                    again=call('POST','/agent-tasks/'+preview['task_ref']+'/action',auth,payload)
                    check('idempotent-confirm',again['handoff_case_ref']==refs[0])
            prefix='/handoff-management/semantic'
            check('cases-created-independently-of-analysis',len(call('GET','/customer-service/service-cases',auth))==5)
            for ref in refs[:3]:
                deadline=time.time()+150
                while time.time()<deadline:
                    p=call('GET',prefix+'/cases/'+ref,ops)
                    if p['indexState'] in {'READY','FAILED'}:break
                    time.sleep(2)
                check('index-'+str(refs.index(ref)),p['indexState']=='READY')
            summary=call('GET',prefix+'/cases/'+refs[0]+'/summary',ops)
            question=summary['summary']['unresolved_question']['text']
            check('specific-unresolved-condition',('视频' in question or '录像' in question) and not any(x in question for x in ['已拒绝','不符合资格','资格不通过']))
            check('insufficient-not-indexed',call('GET',prefix+'/cases/'+refs[3],ops)['quality']=='INSUFFICIENT_CONTEXT')
            private=call('GET',prefix+'/cases/'+refs[4],ops)
            check('privacy-fallback',private['quality']=='INSUFFICIENT_CONTEXT' and '19900000000' not in json.dumps(private) and call('GET',prefix+'/cases/'+refs[4]+'/summary',ops)['state']=='INSUFFICIENT_CONTEXT')
            call('GET',prefix+'/cases/'+refs[0],processor,status=403);check('processor-no-operations-access',True)
            call('GET',prefix+'/cases/'+refs[0],auth,status=401);check('customer-no-operations-access',True)
            search=call('GET',prefix+'/cases/'+refs[0]+'/similar?topK=20',ops)
            own=[x['case']['caseRef'] for x in search['candidates'] if x['case']['caseRef'] in refs]
            check('same-issue-before-different',refs[1] in own and (refs[2] not in own or own.index(refs[1])<own.index(refs[2])))
            check('self-excluded',refs[0] not in [x['case']['caseRef'] for x in search['candidates']])
            group=call('POST',prefix+'/groups',ops,{'requestRef':str(uuid.uuid4()),'title':group_title,'topic':'exchange'})
            group_ref=group['groupRef']
            for ref in refs[:2]:
                body={'requestRef':str(uuid.uuid4()),'caseRef':ref,'version':group['version'],'action':'add','basis':'same_primary_issue'}
                group=call('POST',prefix+'/groups/'+group_ref+'/members',ops,body)
                repeated=call('POST',prefix+'/groups/'+group_ref+'/members',ops,body)
                check('member-idempotent-'+str(refs.index(ref)),group['version']==repeated['version'])
            check('distinct-group-count',group['caseCount']==2)
            call('POST',prefix+'/groups/'+group_ref+'/members',ops,{'requestRef':str(uuid.uuid4()),'caseRef':refs[2],'version':1,'action':'add'},status=409);check('stale-version-rejected',True)
            other=call('POST',prefix+'/groups',ops,{'requestRef':str(uuid.uuid4()),'title':'另一个待核实问题','topic':'exchange'})
            call('POST',prefix+'/groups/'+other['groupRef']+'/members',ops,{'requestRef':str(uuid.uuid4()),'caseRef':refs[0],'version':1,'action':'add'},status=409);check('one-primary-group',True)
            if '--live-model' in sys.argv:
                analysis=call('POST',prefix+'/groups/'+group_ref+'/analyses',ops,{'requestRef':str(uuid.uuid4()),'version':group['version']})
                deadline=time.time()+100
                while time.time()<deadline:
                    group=call('GET',prefix+'/groups/'+group_ref,ops)
                    a=next(x for x in group['analyses'] if x['analysisRef']==analysis['analysisRef'])
                    if a['state'] not in {'PENDING','RUNNING'}:break
                    time.sleep(2)
                check('real-group-draft',a['state']=='DRAFT')
                draft=json.loads(a['result']);check('draft-references',set(draft['evidence_refs'])<=set(refs[:2]))
                call('POST',prefix+'/analyses/'+analysis['analysisRef']+'/review',ops)
                check('human-review',True)
            improvement=call('POST','/handoff-management/improvements',ops,{'caseRef':refs[0],'reason':'answer_or_evidence_insufficient','team':'policy'})['improvementRef']
            for version,state in enumerate(['TRIAGED','IN_PROGRESS','VERIFYING'],1):call('PATCH','/handoff-management/improvements/'+improvement,ops,{'version':version,'state':state})
            call('PATCH','/handoff-management/improvements/'+improvement,ops,{'version':4,'state':'CLOSED','verificationCode':'manual_verified'},status=400);check('no-evidence-no-close',True)
            call('POST',prefix+'/groups/'+group_ref+'/evidence',ops,{'improvementRef':improvement,'version':group['version'],'method':'regression','evidence':'synthetic/semantic-acceptance'})
            call('PATCH','/handoff-management/improvements/'+improvement,ops,{'version':4,'state':'CLOSED','verificationCode':'regression_passed'});check('verified-improvement-closure',True)
            if '--browser' in sys.argv:
                from field_browser_support import BrowserSession
                with BrowserSession(password=password,evidence_dir=ROOT/'tmp/semantic-browser',customer_username='semantic_'+fixture) as browser:
                    browser.operations_username='sops_'+fixture;browser.open_route('operations')
                    browser.page.wait_for("document.body.innerText.includes('发现重复问题')")
                    browser.assert_safe_public_text();check('browser-operations',True)
                    browser.page.evaluate("Array.from(document.querySelectorAll('button')).find(x=>x.textContent==="+json.dumps(group_title)+").click()")
                    browser.page.wait_for("document.body.innerText.includes('个独立案件')");check('browser-group',True)
                    browser.open_customer_conversation(sessions[0],expected_markers=('交接使用的安全背景',));check('browser-safe-preview',True)
            version=summary['summaryVersion']
            correction={'version':version,'customer_goal':'确认没有开箱视频是否可以申请换货','unresolved_question':'没有开箱视频是否影响换货申请尚未明确'}
            call('POST',prefix+'/cases/'+refs[0]+'/summary',ops,correction)
            changed=call('GET',prefix+'/cases/'+refs[0]+'/summary',ops)
            check('human-summary-version',changed['summaryVersion']==version+1 and changed['reviewState']=='HUMAN_REVIEWED')
            call('POST',prefix+'/cases/'+refs[0]+'/summary',ops,correction,status=409);check('stale-summary-rejected',True)
            if '--live-model' in sys.argv:
                group=call('GET',prefix+'/groups/'+group_ref,ops)
                check('changed-summary-invalidates-group-draft',next(x for x in group['analyses'] if x['analysisRef']==analysis['analysisRef'])['state']=='STALE')
            deadline=time.time()+60
            while time.time()<deadline:
                updated=call('GET',prefix+'/cases/'+refs[0],ops)
                if updated['indexState']=='READY':break
                time.sleep(2)
            check('corrected-summary-reindexed',updated['indexState']=='READY')
            check('ledger-settled',summarize_release_events(events()[start:])['unresolvedReservations']==0)
    finally:
        runtime=subprocess.check_output(['docker','inspect','--format','{{index .Config.Labels "org.opencontainers.image.revision"}}','mall-ai-demo-mall-ai-service-1'],cwd=ROOT,text=True).strip()
        report={'scope':'handoff-semantic-phase1','sourceSha256':source_hash(),'runtimeCommit':runtime,'checks':checks,'provider':summarize_release_events(events()[start:]),'fixtureHash':__import__('hashlib').sha256(fixture.encode()).hexdigest()}
        target=ROOT/'tmp'/('handoff-semantic-'+fixture+'.json');target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'report':str(target),'provider':report['provider']}),flush=True)

if __name__=='__main__':
    try:run()
    except Exception as exc:print(json.dumps({'stopped':type(exc).__name__}),flush=True);sys.exit(1)
