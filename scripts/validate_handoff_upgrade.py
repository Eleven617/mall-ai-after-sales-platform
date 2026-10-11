"""Validate the scoped upgrade without relabelling historical live campaigns."""
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from handoff_upgrade_identity import ROOT, source_hash

def validate():
    facts=json.loads((ROOT/'docs/evidence/handoff-upgrade-facts.json').read_text(encoding='utf-8'))
    assert facts['scope']=='human-handoff-2026-10-11'
    assert facts['sourceSha256']==source_hash(), 'Upgrade source identity changed'
    live_path=ROOT/facts['liveReport']
    assert hashlib.sha256(live_path.read_bytes()).hexdigest()==facts['liveReportSha256']
    live=json.loads(live_path.read_text(encoding='utf-8'))
    assert all(item['passed'] for item in live['checks'])
    assert len({item['caseId'] for item in live['checks']})==len(live['checks'])
    required={'real_analysis_succeeded','natural_language_handoff_preview','no_case_before_confirmation',
        'duplicate_confirmation_same_case','operator_cannot_review_case','browser_customer_handoff',
        'browser_operations','browser_processor','restart_no_duplicate_case'}
    assert required<={item['caseId'].removeprefix('handoff-v2-') for item in live['checks']}
    assert live['provider']['providerSuccesses']>0 and live['provider']['providerFailures']==0
    assert live['provider']['unresolvedReservations']==0
    report_path=Path(os.getenv('MALL_FASTAPI_REPORT',str(ROOT/'mall-ai-service/ci-evidence/handoff-fastapi-report.json')))
    if not report_path.is_absolute():report_path=ROOT/report_path
    report=json.loads(report_path.read_text(encoding='utf-8'))
    assert report['runtimeCommit']==facts['runtimeCommit']
    assert report['passed']==facts['pythonPassed'] and report['semanticReportSha256']==facts['pythonSemanticSha256']
    assert report['failures']==report['errors']==report['skipped']==report['exitCode']==0
    junit=Path(os.getenv('MALL_FASTAPI_JUNIT',str(report_path.with_name('handoff-fastapi-junit.xml'))))
    if not junit.is_absolute():junit=ROOT/junit
    assert hashlib.sha256(junit.read_bytes()).hexdigest()==report['junitSha256']
    readme=(ROOT/'README.md').read_text(encoding='utf-8')
    assert 'docs/HANDOFF_UPGRADE_IMPLEMENTATION.md' in readme
    assert '![' not in readme, 'README is deliberately text-only'
    assert facts['historicalEvaluationsRewritten'] is False
    assert subprocess.run(['git','merge-base','--is-ancestor',facts['runtimeCommit'],'HEAD'],cwd=ROOT).returncode==0
    tracked=subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines()
    assert not any(re.search(r'(^|/)\.env$|(^|/)\.env\.(?!example$)|(^|/)(id_rsa|credentials?|.*\.(pem|key|p12))$',path,re.I) for path in tracked)
    assert not any('mall-ai-service/tmp/' in path for path in tracked)
    assert subprocess.run(['git','check-ignore','-q','mall-ai-service/tmp/'],cwd=ROOT).returncode==0
    print('handoff_upgrade_validation PASSED source='+facts['sourceSha256'][:12]+' python='+str(report['passed']))
    return 0

if __name__=='__main__':
    raise SystemExit(validate())
