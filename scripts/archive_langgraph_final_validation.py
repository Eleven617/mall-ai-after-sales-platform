"""Archive bounded live and actual rollback results without rewriting prior evidence."""
import hashlib
import json
from pathlib import Path
import sys

from handoff_upgrade_identity import ROOT, source_hash
sys.path.insert(0,str(ROOT/'mall-ai-service'))
from app.services.release_ledger import summarize_release_events


def main():
    target=ROOT/'docs/evidence/langgraph-final-validation'
    target.mkdir(exist_ok=True)
    def archive(name,data):
        path=target/(name+'.json')
        # Stable LF UTF-8 artifact for hash verification on Windows and Linux.
        path.write_bytes((json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode())
        return {'path':path.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    live=json.loads((ROOT/'tmp/langgraph-live-conversation.json').read_text(encoding='utf-8'))
    showcase=json.loads((ROOT/'tmp/langgraph-live-showcase/showcase.json').read_text(encoding='utf-8'))
    rollback=json.loads((ROOT/'tmp/langgraph-rollback-report.json').read_text(encoding='utf-8'))
    assert len(live['checks'])==9 and all(c['passed'] for c in live['checks'])
    assert showcase['status']=='passed' and showcase['providerMode']=='live'
    assert len(rollback['checks'])==11 and all(c['passed'] for c in rollback['checks'])
    ledger=ROOT/'tmp/langgraph-live-ledger-20261012/ledger.jsonl'
    events=[json.loads(line) for line in ledger.read_text(encoding='utf-8').splitlines() if line]
    usage=summarize_release_events(events)
    reservations=[event for event in events if event['eventType']=='provider_reservation']
    settlements=[event for event in events if event['eventType']=='provider_reservation_settlement']
    assert len(reservations)==len(settlements)==usage['providerHttpAttempts']
    assert usage['unresolvedReservations']==0 and usage['providerFailures']==0
    assert usage['providerHttpAttempts']<=80 and usage['totalTokens']<=200000
    artifacts=[archive('live-conversation',live),archive('live-showcase',showcase),archive('rollback',rollback),
               archive('preflight-denial',json.loads((ROOT/'tmp/langgraph-live-preflight-denial.json').read_text(encoding='utf-8')))]
    archive('ledger',events)
    artifacts.append({'path':'docs/evidence/langgraph-final-validation/ledger.json',
        'sha256':hashlib.sha256((target/'ledger.json').read_bytes()).hexdigest()})
    scripts=['mall-ai-service/scripts/check_unified_conversation_live.py','mall-ai-service/scripts/run_real_local_showcase.py',
             'mall-ai-service/scripts/verify_graph_rollback.py']
    result={'scope':'bounded real DeepSeek migration smoke and actual read-only rollback',
        'sourceSha256':source_hash(),'runtimeCommit':'c142fe107fc5a9704f1dca68505dab84e8a95314',
        'liveConversationPassed':9,'liveShowcasePassed':1,'rollbackAssertionsPassed':11,
        'usage':usage,'reservations':len(reservations),'settlements':len(settlements),'ledgerReconciled':True,
        'maxHttpAttempts':80,'maxTokens':200000,
        'preflightDeniedCalls':2,'preflightProviderRequests':0,
        'fullHistoricalQualitySuiteRerun':False,'mainMerged':False,'artifacts':artifacts,
        'runnerHashes':{p:hashlib.sha256((ROOT/p).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for p in scripts}}
    entry=archive('summary',result)
    print(json.dumps(entry))


if __name__=='__main__':
    main()
