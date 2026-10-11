"""Java-only handoff writes. Unknown outcomes are queried, never rekeyed."""
import httpx
from app.config import settings
from app.schemas.human_handoff import HandoffContext, HandoffResult

class HandoffUnavailable(RuntimeError):
    pass

def record_handoff_event(context:HandoffContext,authorization:str,event:str):
    try:
        response=httpx.post(settings.mall_api_base_url.rstrip('/')+'/ai/human-handoffs/events/'+context.request_ref+'/'+event,
            headers={'Authorization':authorization,'X-AI-Handoff-Key':settings.ai_case_handoff_service_key},timeout=settings.mall_api_timeout_seconds)
        return response.status_code==200
    except httpx.HTTPError:
        return False

def handoff_request(context: HandoffContext, content_hash: str, authorization: str, *, lookup=False):
    path='/ai/human-handoffs'
    if lookup:
        path += '/by-request/' + context.request_ref
    try:
        response=httpx.request('GET' if lookup else 'POST', settings.mall_api_base_url.rstrip('/')+path,
            headers={'Authorization':authorization,'X-AI-Handoff-Key':settings.ai_case_handoff_service_key},
            json=None if lookup else {
                'requestRef':context.request_ref,'scopeKey':context.scope_key,'contentHash':content_hash,
                'triggerSource':context.source,'entryChannel':context.channel,'businessTopic':context.topic,
                'customerReason':context.reason,'taskRef':context.linked_task_ref,'stage':context.stage,
                'planVersion':context.plan_version,'completedSteps':context.completed_steps,'verifiedEvidenceCount':context.verified_evidence_count,
            }, timeout=settings.mall_api_timeout_seconds)
        data=response.json()
        if response.status_code != 200 or data.get('code') != 200:
            raise HandoffUnavailable('交接结果暂不可确认')
        return HandoffResult.model_validate(data['data'])
    except (httpx.HTTPError,ValueError,KeyError) as exc:
        raise HandoffUnavailable('交接结果暂不可确认') from exc
