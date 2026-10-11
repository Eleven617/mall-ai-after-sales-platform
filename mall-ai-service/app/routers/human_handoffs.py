from fastapi import APIRouter, Header, HTTPException
from app.schemas.human_handoff import HandoffPrepare
from app.schemas.agent_task import AgentTaskPublicView
from app.services.mall_client import get_current_member, MallAuthenticationError
from app.services.conversation_history_client import get_customer_conversation, ConversationHistoryError
from app.runtime.task_runtime import get_task_runtime, TaskRuntimeError
from app.runtime.task_store import TaskStoreAccessDenied
from app.services.human_handoff_client import HandoffUnavailable

router=APIRouter(prefix='/human-handoffs',tags=['human-handoffs'])

@router.post('/prepare',response_model=AgentTaskPublicView)
def prepare(request:HandoffPrepare,authorization:str|None=Header(default=None)):
    try:
        member=get_current_member(authorization)
        get_customer_conversation(request.session_id,authorization)
        runtime=get_task_runtime()
        result=runtime.prepare_handoff(request,member_id=member.member_id,authorization=authorization)
        return result.view
    except (MallAuthenticationError,ConversationHistoryError) as exc:
        raise HTTPException(status_code=exc.status_code,detail=str(exc)) from exc
    except TaskStoreAccessDenied as exc:
        raise HTTPException(status_code=404,detail='事项不存在') from exc
    except TaskRuntimeError as exc:
        raise HTTPException(status_code=exc.status_code,detail=str(exc)) from exc

@router.get('/{task_ref}/result',response_model=AgentTaskPublicView)
def result(task_ref:str,authorization:str|None=Header(default=None)):
    try:
        member=get_current_member(authorization)
        return get_task_runtime().reconcile_handoff(task_ref=task_ref,member_id=member.member_id,authorization=authorization).view
    except MallAuthenticationError as exc:
        raise HTTPException(status_code=exc.status_code,detail=str(exc)) from exc
    except TaskStoreAccessDenied as exc:
        raise HTTPException(status_code=404,detail='事项不存在') from exc
    except HandoffUnavailable as exc:
        raise HTTPException(status_code=503,detail='结果仍待确认，请稍后查询原事项。') from exc
    except TaskRuntimeError as exc:
        raise HTTPException(status_code=exc.status_code,detail=str(exc)) from exc
