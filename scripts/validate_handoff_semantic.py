"""Validate version-scoped semantic handoff evidence without rewriting history."""
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from handoff_upgrade_identity import ROOT, source_hash

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def validate():
    facts=read(ROOT/'docs/evidence/handoff-semantic-facts.json')
    assert facts['scope']=='handoff-semantic-phase1'
    assert facts['sourceSha256']==source_hash(),'Semantic source identity changed'
    path=ROOT/facts['liveReport'];live=read(path)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==facts['liveReportSha256']
    assert live['sourceSha256']==facts['sourceSha256'] and live['runtimeCommit']==facts['runtimeCommit']
    assert live['checks'] and all(x['passed'] for x in live['checks'])
    names={x['caseId'] for x in live['checks']}
    assert len(names)==len(live['checks'])
    assert {'semantic-specific-unresolved-condition','semantic-same-issue-before-different','semantic-real-group-draft','semantic-verified-improvement-closure','semantic-browser-group','semantic-privacy-fallback','semantic-one-primary-group'}<=names
    assert live['provider']['providerSuccesses']>=4 and live['provider']['providerFailures']==0
    assert live['provider']['unresolvedReservations']==0
    path=Path(os.getenv('MALL_FASTAPI_REPORT',str(ROOT/'mall-ai-service/ci-evidence/semantic-fastapi-report.json')))
    if not path.is_absolute():path=ROOT/path
    report=read(path)
    assert report['runtimeCommit']==facts['runtimeCommit']
    assert report['passed']==facts['pythonPassed'] and report['semanticReportSha256']==facts['pythonSemanticSha256']
    assert report['failures']==report['errors']==report['skipped']==report['exitCode']==0
    junit=Path(os.getenv('MALL_FASTAPI_JUNIT',str(path.with_name('semantic-fastapi-junit.xml'))))
    if not junit.is_absolute():junit=ROOT/junit
    assert hashlib.sha256(junit.read_bytes()).hexdigest()==report['junitSha256']
    assert facts['historicalEvaluationsRewritten'] is False
    assert subprocess.run(['git','merge-base','--is-ancestor',facts['runtimeCommit'],'HEAD'],cwd=ROOT).returncode==0
    readme=(ROOT/'README.md').read_text(encoding='utf-8')
    assert '![' not in readme and 'docs/HANDOFF_SEMANTIC_IMPLEMENTATION.md' in readme
    tracked=subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines()
    assert not any(re.search(r'(^|/)\.env$|(^|/)\.env\.(?!example$)|(^|/)(id_rsa|credentials?|.*\.(pem|key|p12))$',p,re.I) for p in tracked)
    assert not any('mall-ai-service/tmp/' in p for p in tracked)
    assert subprocess.run(['git','check-ignore','-q','mall-ai-service/tmp/'],cwd=ROOT).returncode==0
    print('handoff_semantic_validation PASSED source='+facts['sourceSha256'][:12]+' python='+str(report['passed']))
    return 0

if __name__=='__main__':raise SystemExit(validate())
