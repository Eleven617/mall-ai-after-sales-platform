"""Archive safe machine results and bind named migration assertions to them."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from handoff_upgrade_identity import ROOT, source_hash
from validate_langgraph_migration import REQUIRED_ENVIRONMENT_CHECKS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--handoff-report', type=Path, required=True)
    parser.add_argument('--persistence-database', required=True)
    args = parser.parse_args()
    assert args.persistence_database.startswith('mall_graph_acceptance_') and args.persistence_database.replace('_', '').isalnum()
    target = ROOT/'docs/evidence/langgraph-acceptance'
    target.mkdir(exist_ok=True)
    artifacts = []
    checks = {}
    def archive(name, data):
        path = target/(name+'.json')
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        artifacts.append({'path': path.relative_to(ROOT).as_posix(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        return artifacts[-1]['path']
    def add(name, passed, evidence):
        assert passed, name
        assert name not in checks, name
        checks[name] = {'caseId': name, 'passed': True, 'evidence': evidence}
    def container(code):
        result = subprocess.run(['docker','compose','exec','-T','mall-ai-service','python','-c',code], cwd=ROOT,
            capture_output=True, text=True, encoding='utf-8', check=True)
        return json.loads(result.stdout)
    rows = container("from pymongo import MongoClient; from app.config import settings; import json; "
        f"print(json.dumps(list(MongoClient(settings.agent_task_mongo_url)[{args.persistence_database!r}].acceptance_reports.find({{}},{{'_id':0}}))))")
    assert {row['phase'] for row in rows} == {'prepare', 'recover'}
    path = archive('persistence', rows)
    for row in rows:
        for check in row['checks']:
            add(check['caseId'], check['passed'], path)
    for name, filename in [('java-recovery','tmp/langgraph-java-recovery.json'), ('capabilities','tmp/langgraph-capabilities.json')]:
        data = json.loads((ROOT/filename).read_text(encoding='utf-8'))
        assert data['externalProviderRequests'] == 0
        path = archive(name,data)
        for check in data['checks']:
            add(check['caseId'],check['passed'],path)
    showcase = json.loads((ROOT/'tmp/langgraph-migration-showcase/showcase.json').read_text(encoding='utf-8'))
    assert showcase['status']=='passed' and showcase['providerMode']=='deterministic'
    path = archive('showcase',showcase)
    chains = {chain['scenario']:chain for chain in showcase['chains']}
    main = chains['main_open_task_closed_loop']
    add('long_task',main['javaRechecked'] and main['confirmedWrite'] and main['statusReadback'],path)
    add('browser_task_projection',showcase['browserFrameCount']==8 and showcase['crossScenarioFramesDistinct'],path)
    handoff = json.loads(args.handoff_report.read_text(encoding='utf-8'))
    assert handoff['offlineWorker'] and handoff['provider']['providerHttpAttempts']==0
    handoff_checks = {check['caseId']:check['passed'] for check in handoff['checks']}
    assert handoff_checks and all(handoff_checks.values())
    path = archive('handoff',handoff)
    add('human_handoff',handoff_checks['handoff-v2-confirmed_waiting_human'] and handoff_checks['handoff-v2-restart_original_case_reconciled'],path)
    add('operations_analysis',handoff_checks['handoff-v2-operations_capability_graph'],path)
    add('proposal_amend_cancel',main['draftAmended'] and main['oldRevisionHttpStatus']==409 and handoff_checks['handoff-v2-proposal_withdraw_no_write'],path)
    guard = container("import os,json; print(json.dumps({'offline':os.getenv('MALL_RUNTIME_PROVIDER_MODE')=='deterministic',"
        "'liveDisabled':os.getenv('MALL_PROVIDER_LIVE_AUTH')=='0','workerDisabled':os.getenv('MALL_HANDOFF_SEMANTIC_ENABLED')=='0',"
        "'modelKeysAbsent':not os.getenv('DEEPSEEK_API_KEY') and not os.getenv('OPENAI_API_KEY')}))")
    path=archive('provider-guard',guard)
    add('offline_provider_enforced',all(guard.values()),path)
    assert REQUIRED_ENVIRONMENT_CHECKS <= checks.keys()
    runners = ['mall-ai-service/scripts/verify_graph_persistence.py', 'mall-ai-service/scripts/verify_graph_java_recovery.py',
               'mall-ai-service/scripts/verify_graph_capabilities.py','mall-ai-service/scripts/verify_handoff_upgrade_live.py',
               'mall-ai-service/scripts/run_real_local_showcase.py']
    report = {'scope':'langgraph-unification-v1','sourceSha256':source_hash(), 'executionState':'dirty_worktree',
        'storage':'real_mongo','java':'real_local','externalProviderRequests':0,'externalProviderTokens':0,
        'modelBoundary':'scripted/deterministic; not model-quality evidence','checks':list(checks.values()),
        'artifacts':artifacts,'runnerHashes':{p:hashlib.sha256((ROOT/p).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for p in runners}}
    result = target/'environment.json'
    result.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'report':result.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(result.read_bytes()).hexdigest(),
                      'namedAssertions':len(checks),'sourceSha256':report['sourceSha256']}))


if __name__ == '__main__':
    main()
