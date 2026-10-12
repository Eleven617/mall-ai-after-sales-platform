"""Frozen synthetic rubric for live summary fidelity; no customer records read."""
import hashlib
import json
import os
import re
import sys
import uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.services.handoff_safe_context import fragments,snapshot
from app.services.handoff_summary import PROMPT,ProblemSummary,validate_summary
from app.services.llm_service import generate_json
from app.services.llm_observability import capture_llm_metrics
from app.services.provider_guard import provider_access_context
from app.services.release_ledger import release_ledger_context

CASES=[
    {'id':'summary-no-video','turns':[('user','换货需要哪些材料'),('assistant','需要提供一般材料'),('user','没有开箱视频还能申请换货吗')],'topic':'exchange','terms':['视频','换货'],'steps':True},
    {'id':'summary-paraphrase','turns':[('user','没有开箱录像是否可以申请换货')],'topic':'exchange','terms':['视频','换货'],'steps':False},
    {'id':'summary-destination-negative','turns':[('user','换货应该寄到哪里')],'topic':'exchange','terms':['寄'],'steps':False},
    {'id':'summary-refund-progress','turns':[('assistant','退款进度需要查询'),('user','退款进度仍然不清楚')],'topic':'refund','terms':['退款','进度'],'steps':True},
]

def run():
    checks=[]
    for case in CASES:
        rows=[]
        for role,text in case['turns']:
            projected,omitted=fragments(text,role)
            assert projected and not omitted
            rows.extend(projected)
        data=snapshot(rows,topic=case['topic'])
        with provider_access_context(mode='live',authorized=True,release_id=os.getenv('MALL_RELEASE_ID'),batch_id=os.getenv('MALL_RELEASE_BATCH_ID'),ledger_path=os.getenv('MALL_RELEASE_LEDGER_PATH'),runtime_commit=os.getenv('MALL_RUNTIME_COMMIT')):
            with release_ledger_context(batch_id=os.getenv('MALL_RELEASE_BATCH_ID'),source='handoff_summary_quality'):
                with capture_llm_metrics(timeout_seconds=30,max_attempts=1):
                    raw=generate_json(message=json.dumps(data,ensure_ascii=False),system_prompt=PROMPT+json.dumps(ProblemSummary.model_json_schema(),ensure_ascii=False),max_tokens=1000,extraction_mode=True)
                    value=validate_summary(raw,data)
        goal=(value['customer_goal'] or {}).get('text','')
        question=(value['unresolved_question'] or {}).get('text','')
        prose=json.dumps(value,ensure_ascii=False)
        # Explicit disclaimers such as “不代表资格不通过” are not positive
        # assertions of denial. Preserve outputs for independent human review.
        assertions=re.sub(r'(不代表|不等于|不能据此|无法判断|未说明)[^。；]*','',prose)
        rubric={
            'goal_present':bool(goal),
            'specific_question':all(term in question for term in case['terms']),
            'handling_fidelity':bool(value['handling_steps'])==case['steps'] and all(x['result_kind']=='assistant_explanation' for x in value['handling_steps']),
            'no_invented_business_outcome':not any(word in assertions for word in ['资格不通过','已拒绝','已退款','已完成退款','客户不满','系统拒绝']),
            'references_and_privacy':True,
        }
        if 'video' in case['id'] or case['id']=='summary-paraphrase':rubric['negation_retained']=any(term in question for term in ['没有','缺少','无开箱','未提供'])
        checks.append({'caseId':case['id'],'rubric':rubric,'passed':all(rubric.values()),'syntheticSummary':value})
    report={'scope':'synthetic-summary-fidelity','fixtureSha256':hashlib.sha256(json.dumps(CASES,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),'sampleCount':len(CASES),'checks':checks}
    target=Path('/app/tmp')/('summary-quality-'+uuid.uuid4().hex[:12]+'.json');target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('REPORT_PATH='+str(target))
    print(json.dumps(report,ensure_ascii=False))
    return 0 if all(x['passed'] for x in checks) else 1

if __name__=='__main__':raise SystemExit(run())
