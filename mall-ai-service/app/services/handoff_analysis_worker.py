"""Bounded, leased Java projections. No customer JWT and no business writes.

Run --once for a bounded invocation; scheduling can invoke repeatedly. A failed
worker lease expires in Java. The controller has only analysis capability.
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
import httpx
from pydantic import BaseModel, ConfigDict
from app.config import settings
from app.schemas.human_handoff import Reason
from app.services.llm_service import generate_json
from app.services.llm_observability import capture_llm_metrics
from app.services.provider_guard import provider_access_context
from app.services.release_ledger import release_ledger_context

class Classification(BaseModel):
    model_config=ConfigDict(extra='forbid')
    reason: Reason

def run_once():
    key=os.getenv('AI_HANDOFF_ANALYSIS_SERVICE_KEY','') or (hashlib.sha256((settings.ai_case_handoff_service_key+':handoff-analysis-v1').encode()).hexdigest() if settings.ai_case_handoff_service_key else '')
    if not key:
        print('analysis_unavailable: missing_service_identity');return 2
    with httpx.Client(timeout=10,trust_env=False) as client:
        base=settings.mall_admin_api_base_url.rstrip('/')+'/ai/handoff-management/internal'
        def call(path,body=None):
            response=client.post(base+path,headers={'X-Handoff-Analysis-Key':key},json=body)
            response.raise_for_status();payload=response.json()
            if payload.get('code')!=200:raise RuntimeError('analysis_java_rejected')
            return payload.get('data')
        item=call('/lease')
        if not item:
            print('analysis_idle');return 0
        projection={k:item.get(k) for k in ('topic','customerReason','stage','source')}
        projection['progress']={k:(item.get('context') or {}).get(k) for k in ('planVersion','completedSteps','verifiedEvidenceCount')}
        state='SUCCEEDED';reason=None
        try:
            with provider_access_context(mode=os.getenv('MALL_RUNTIME_PROVIDER_MODE','offline'),authorized=os.getenv('MALL_PROVIDER_LIVE_AUTH')=='1',release_id=os.getenv('MALL_RELEASE_ID'),batch_id=os.getenv('MALL_RELEASE_BATCH_ID'),ledger_path=os.getenv('MALL_RELEASE_LEDGER_PATH'),runtime_commit=os.getenv('MALL_RUNTIME_COMMIT')):
                with release_ledger_context(batch_id=os.getenv('MALL_RELEASE_BATCH_ID'),source='handoff_analysis'):
                    with capture_llm_metrics(timeout_seconds=30,max_attempts=1):
                        value=generate_json(message=json.dumps(projection),system_prompt='分类客户转人工原因。只依据给定结构化投影，客户选择是陈述而非已核实根因。未说明时用unspecified，不猜技术根因。仅输出JSON：'+json.dumps(Classification.model_json_schema()),temperature=0,max_tokens=800)
                        reason=Classification.model_validate(value,strict=True).reason
                        if projection['customerReason']=='unspecified' and reason!='unspecified':
                            raise ValueError('unsupported_inference')
                        if projection['customerReason']!='unspecified' and reason!=projection['customerReason']:
                            raise ValueError('customer_reason_overridden')
        except Exception:
            state='UNAVAILABLE' if not settings.deepseek_api_key else 'FAILED'
        projection_hash=hashlib.sha256(json.dumps(projection,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        call('/result',{'caseRef':item['caseRef'],'lease':item['lease'],'state':state,'reason':reason,
            'inputHash':projection_hash,'modelVersion':settings.deepseek_model})
        print(json.dumps({'analysisState':state,'rawTextRetained':False}));return 0 if state=='SUCCEEDED' else 1

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--once',action='store_true');parser.parse_args()
    try:sys.exit(run_once())
    except Exception:print('analysis_worker_failed');sys.exit(1)
