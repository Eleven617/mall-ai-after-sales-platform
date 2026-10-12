"""Actual local read-only rollback and return-to-new-image drill; no model calls."""
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import sys
import uuid

import httpx
from bootstrap_live_demo import DemoAccount, _ensure_login

ROOT = Path(__file__).resolve().parents[2]
BASE = 'http://127.0.0.1:5173/api'


def command(args):
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=180)
    assert result.returncode == 0, 'rollback_command_failed'
    return result.stdout.strip()


def fingerprint():
    code = "from pymongo import MongoClient; from app.config import settings; import json,hashlib; c=MongoClient(settings.agent_task_mongo_url)[settings.agent_task_mongo_database]; names=[settings.agent_task_mongo_collection,'orchestration_checkpoints_v1','orchestration_writes_v1']; h=hashlib.sha256(); counts={}; " \
        "\nfor name in names:\n rows=list(c[name].find({},{'_id':0}).sort('_id',1)); counts[name]=len(rows); h.update(json.dumps(rows,sort_keys=True,default=str).encode())\nprint(json.dumps({'sha256':h.hexdigest(),'counts':counts}))"
    return json.loads(command(['docker','compose','exec','-T','mall-ai-service','python','-c',code]))


def main():
    checks=[]
    def check(name, passed):
        assert passed, name
        checks.append({'caseId':name,'passed':True})
    with httpx.Client(timeout=25,trust_env=False) as client:
        account=DemoAccount('rollback','rollback_'+uuid.uuid4().hex[:12],secrets.token_urlsafe(24),'194'+str(uuid.uuid4().int%100000000).zfill(8))
        auth,_=_ensure_login(client,'http://127.0.0.1:8085',account)
        headers={'Authorization':auth}
        before=fingerprint()
        old_image=command(['docker','image','inspect','mall-ai-langgraph-rollback:20261012','--format','{{.Id}}'])
        recovered=False
        try:
            command(['docker','compose','stop','-t','45','mall-ai-web','mall-ai-service'])
            command(['docker','compose','-f','docker-compose.yml','-f','tmp/langgraph-rollback.compose.yml',
                     'up','-d','--no-build','--no-deps','--wait','--wait-timeout','120','mall-ai-service','mall-ai-web'])
            container=command(['docker','compose','ps','-q','mall-ai-service'])
            running_image=command(['docker','inspect','--format','{{.Image}}',container])
            check('old_image_actual_cutover',running_image==old_image)
            check('rollback_health',client.get(BASE+'/health/ready').status_code==200)
            check('rollback_java_identity_read',client.get(BASE+'/auth/me',headers=headers).status_code==200)
            check('rollback_java_business_read',client.get(BASE+'/customer-service/after-sales-applications',headers=headers).status_code==200)
            check('rollback_mutation_rejected',client.post(BASE+'/customer-service',headers=headers,json={'message':'synthetic'}).status_code==503)
            check('rollback_task_executor_closed',client.get(BASE+'/agent-tasks',headers=headers).status_code==503)
            ports=command(['docker','inspect','--format','{{json .NetworkSettings.Ports}}',container])
            check('rollback_direct_ai_not_exposed','HostPort' not in ports)
            guard=json.loads(command(['docker','compose','exec','-T','mall-ai-service','python','-c',
                "import os,json; print(json.dumps({'liveDisabled':os.getenv('MALL_PROVIDER_LIVE_AUTH')=='0','workerDisabled':os.getenv('MALL_HANDOFF_SEMANTIC_ENABLED')=='0'}))"]))
            check('rollback_model_disabled',all(guard.values()))
        finally:
            command(['docker','compose','stop','-t','45','mall-ai-web','mall-ai-service'])
            command(['docker','compose','-f','docker-compose.yml','-f','tmp/langgraph-acceptance.compose.yml',
                     'up','-d','--no-build','--no-deps','--wait','--wait-timeout','120','mall-ai-service','mall-ai-web'])
            recovered=True
        after=fingerprint()
        check('new_graph_storage_preserved',before==after)
        check('new_graph_api_restored',recovered and client.get(BASE+'/agent-tasks',headers=headers).status_code==200)
        check('new_runtime_restored',client.get(BASE+'/health/version').json()['providerMode']=='deterministic')
        report={'checks':checks,'externalProviderRequests':0,'rollbackImage':old_image,
                'storageBefore':before,'storageAfter':after,'volumesDeleted':False,
                'scope':'actual old image with mutation/task endpoints closed, then new image restore'}
        (ROOT/'tmp/langgraph-rollback-report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(report))


if __name__=='__main__':
    main()
