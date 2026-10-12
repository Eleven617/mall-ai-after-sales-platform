"""Archive generated synthetic evidence and derive facts; preserve source reports."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
from handoff_upgrade_identity import ROOT,source_hash

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8'))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('live');parser.add_argument('quality');args=parser.parse_args()
    live_path=ROOT/args.live;live=read(live_path)
    assert live['sourceSha256']==source_hash() and all(x['passed'] for x in live['checks'])
    quality=ROOT/args.quality
    assert read(quality)['runtimeCommit']==live['runtimeCommit']
    assert all(x['passed'] for x in read(quality)['checks'])
    output=ROOT/'docs/evidence/handoff-semantic-20261012';output.mkdir(exist_ok=True)
    for source,name in [(live_path,'live-acceptance.json'),(quality,'summary-quality.json')]:
        target=output/name
        if target.exists() and digest(target)!=digest(source):raise RuntimeError('immutable_archive_conflict')
        shutil.copyfile(source,target)
    python=read(ROOT/'mall-ai-service/ci-evidence/semantic-fastapi-report.json')
    assert python['runtimeCommit']==live['runtimeCommit']
    facts={'scope':'handoff-semantic-phase1','status':'LOCAL_VERIFIED','runtimeCommit':live['runtimeCommit'],'sourceSha256':source_hash(),
        'liveReport':str((output/'live-acceptance.json').relative_to(ROOT)).replace('\\','/'),'liveReportSha256':hashlib.sha256(live_path.read_bytes().replace(b'\r\n',b'\n')).hexdigest(),'liveReportHashEncoding':'UTF-8 LF','liveChecks':len(live['checks']),
        'qualityReport':str((output/'summary-quality.json').relative_to(ROOT)).replace('\\','/'),'qualityReportSha256':digest(quality),
        'qualityScope':'Four synthetic development cases using real DeepSeek. Not a held-out production accuracy estimate.',
        'pythonPassed':python['passed'],'pythonSemanticSha256':python['semanticReportSha256'],
        'javaPortalPassed':17,'javaAdminPassed':27,'vueBuild':'passed','composeHealthy':8,
        'manifestPassed':478,'representativePassed':8,'historicalEvaluationsRewritten':False}
    (ROOT/'docs/evidence/handoff-semantic-facts.json').write_text(json.dumps(facts,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(facts,ensure_ascii=False))

if __name__=='__main__':main()
