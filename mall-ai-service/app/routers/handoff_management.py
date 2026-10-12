"""Role-separated proxy: Java validates every read and mutation again."""
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
import httpx
from app.config import settings
from app.schemas.human_handoff import Reason

router=APIRouter(prefix='/handoff-management',tags=['handoff-management'])

class Review(BaseModel):
    model_config=ConfigDict(extra='forbid')
    reason: Reason
    version: int = Field(ge=0)

class Improvement(BaseModel):
    model_config=ConfigDict(extra='forbid')
    caseRef: str | None = Field(default=None,pattern=r'^[a-f0-9-]{36}$')
    reason: Reason = 'unspecified'
    team: Literal['engineering','policy','service'] = 'service'
    state: Literal['OPEN','TRIAGED','IN_PROGRESS','VERIFYING','CLOSED'] = 'OPEN'
    version: int = Field(default=0,ge=0)
    verificationCode: Literal['not_verified','regression_passed','manual_verified','no_change_needed'] = 'not_verified'

def proxy(method,path,authorization,**kwargs):
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401,'请先登录对应工作台')
    try:
        response=httpx.request(method,settings.mall_admin_api_base_url.rstrip('/')+'/ai/handoff-management'+path,headers={'Authorization':authorization},timeout=10,**kwargs)
        data=response.json()
    except (httpx.HTTPError,ValueError) as exc:
        raise HTTPException(503,'交接管理服务暂不可用') from exc
    if response.status_code>=400 or data.get('code')!=200:
        status=response.status_code if response.status_code>=400 else data.get('code',502)
        raise HTTPException(status if status in {400,401,403,404,409} else 502,'请求未完成：请检查身份、权限或版本并刷新。')
    return data.get('data')

@router.get('')
def page(days:int=Query(7),page:int=Query(1,ge=1),size:int=Query(20,ge=1,le=50),topic:str|None=None,source:str|None=None,reason:str|None=None,authorization:str|None=Header(default=None)):
    return proxy('GET','',authorization,params={k:v for k,v in locals().items() if k!='authorization' and v is not None})

@router.get('/cases/{ref}')
def detail(ref:str,authorization:str|None=Header(default=None)):
    return proxy('GET','/cases/'+ref,authorization)

@router.get('/processor/cases/{ref}')
def processor(ref:str,authorization:str|None=Header(default=None)):
    return proxy('GET','/processor/cases/'+ref,authorization)

@router.post('/processor/cases/{ref}/review')
def review(ref:str,request:Review,authorization:str|None=Header(default=None)):
    return proxy('POST','/processor/cases/'+ref+'/review',authorization,json=request.model_dump())

@router.get('/improvements')
def improvements(authorization:str|None=Header(default=None)):
    return proxy('GET','/improvements',authorization)

@router.post('/improvements')
def create(request:Improvement,authorization:str|None=Header(default=None)):
    return proxy('POST','/improvements',authorization,json=request.model_dump())

@router.patch('/improvements/{ref}')
def update(ref:str,request:Improvement,authorization:str|None=Header(default=None)):
    return proxy('PATCH','/improvements/'+ref,authorization,json=request.model_dump())

@router.post('/retention')
def retention(dryRun:bool=True,days:int=Query(90,ge=90,le=3650),eventDays:int=Query(365,ge=365,le=3650),authorization:str|None=Header(default=None)):
    return proxy('POST','/retention',authorization,params={'dryRun':str(dryRun).lower(),'days':days,'eventDays':eventDays})

@router.post('/cases/{ref}/retention-hold')
def retention_hold(ref:str,held:bool,authorization:str|None=Header(default=None)):
    return proxy('POST','/cases/'+ref+'/retention-hold',authorization,params={'held':str(held).lower()})

class GroupCreate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    requestRef: str=Field(pattern=r'^[a-f0-9-]{36}$')
    title: str=Field(min_length=2,max_length=120)
    topic: str=Field(max_length=32)

class GroupMember(BaseModel):
    model_config=ConfigDict(extra='forbid')
    requestRef: str=Field(pattern=r'^[a-f0-9-]{36}$')
    caseRef: str=Field(pattern=r'^[a-f0-9-]{36}$')
    version: int=Field(ge=1)
    action: Literal['add','remove','reject_related','reject_unrelated']
    basis: Literal['same_primary_issue','same_failure_boundary']='same_primary_issue'

class AnalysisRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    requestRef: str=Field(pattern=r'^[a-f0-9-]{36}$')
    version: int=Field(ge=1)

class VerificationEvidence(BaseModel):
    model_config=ConfigDict(extra='forbid')
    improvementRef: str=Field(pattern=r'^[a-f0-9-]{36}$')
    version: int=Field(ge=1)
    analysisRef: str|None=Field(default=None,pattern=r'^[a-f0-9-]{36}$')
    method: Literal['regression','manual_review','before_after_observation']
    evidence: str=Field(pattern=r'^[a-zA-Z0-9_./:-]{3,160}$')

@router.get('/semantic/coverage')
def coverage(days:int=30,authorization:str|None=Header(default=None)):
    return proxy('GET','/semantic/coverage',authorization,params={'days':days})

@router.post('/semantic/rebuild')
def rebuild(authorization:str|None=Header(default=None)):
    return proxy('POST','/semantic/rebuild',authorization)

@router.get('/semantic/cases/{ref}')
def problem(ref:str,authorization:str|None=Header(default=None)):
    return proxy('GET','/semantic/cases/'+ref,authorization)

@router.get('/semantic/cases/{ref}/summary')
def summary(ref:str,authorization:str|None=Header(default=None)):
    return proxy('GET','/semantic/cases/'+ref+'/summary',authorization)

@router.post('/semantic/cases/{ref}/summary/retry')
def retry_summary(ref:str,version:int=Query(ge=0),authorization:str|None=Header(default=None)):
    return proxy('POST','/semantic/cases/'+ref+'/summary/retry',authorization,params={'version':version})

class SummaryCorrection(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version:int=Field(ge=1)
    customer_goal:str=Field(min_length=1,max_length=120)
    unresolved_question:str=Field(min_length=1,max_length=240)

@router.post('/semantic/cases/{ref}/summary')
def correct_summary(ref:str,request:SummaryCorrection,authorization:str|None=Header(default=None)):
    from app.services.handoff_safe_context import safe_tokens
    from app.services.handoff_summary import projection
    if not safe_tokens(request.customer_goal) or not safe_tokens(request.unresolved_question):raise HTTPException(400,'请使用不含身份信息的简短业务描述；无法安全识别的文本不会保存')
    current=proxy('GET','/semantic/cases/'+ref+'/summary',authorization)
    if current['summaryVersion']!=request.version or current['state']!='SUCCEEDED':raise HTTPException(409,'摘要版本已变化或尚未生成')
    value=current['summary']
    if not value.get('customer_goal') or not value.get('unresolved_question'):raise HTTPException(409,'缺少可供纠正的来源，请保持内容不足状态')
    value['customer_goal']['text']=request.customer_goal;value['unresolved_question']['text']=request.unresolved_question
    p=projection(value)
    return proxy('POST','/semantic/cases/'+ref+'/summary',authorization,json={'version':request.version,'summary':value,'projection':p,'projectionHash':p['projection_hash'],'quality':p['content_quality']})

@router.get('/semantic/cases/{ref}/similar')
def similar(ref:str,days:int=30,crossTopic:bool=False,topK:int=Query(5,ge=1,le=20),authorization:str|None=Header(default=None)):
    from app.services.handoff_semantic import similar as search
    try:return search(ref,authorization,days,crossTopic,topK)
    except HTTPException:raise
    except Exception as exc:raise HTTPException(503,'相似索引暂不可用，仍可人工筛选与归组') from exc

@router.get('/semantic/groups')
def groups(authorization:str|None=Header(default=None)):
    return proxy('GET','/semantic/groups',authorization)

@router.post('/semantic/groups')
def create_group(request:GroupCreate,authorization:str|None=Header(default=None)):
    return proxy('POST','/semantic/groups',authorization,json=request.model_dump())

@router.get('/semantic/groups/{ref}')
def group(ref:str,authorization:str|None=Header(default=None)):
    return proxy('GET','/semantic/groups/'+ref,authorization)

@router.post('/semantic/groups/{ref}/members')
def member(ref:str,request:GroupMember,authorization:str|None=Header(default=None)):
    return proxy('POST','/semantic/groups/'+ref+'/members',authorization,json=request.model_dump())

@router.post('/semantic/groups/{ref}/analyses')
def analyze(ref:str,request:AnalysisRequest,authorization:str|None=Header(default=None)):
    import os
    if os.getenv('MALL_HANDOFF_GROUP_ANALYSIS_ENABLED','0')!='1':raise HTTPException(409,'组分析尚未启用；可以继续人工归组与改进')
    return proxy('POST','/semantic/groups/'+ref+'/analyses',authorization,json=request.model_dump())

@router.post('/semantic/analyses/{ref}/review')
def review_analysis(ref:str,authorization:str|None=Header(default=None)):
    return proxy('POST','/semantic/analyses/'+ref+'/review',authorization)

@router.post('/semantic/groups/{ref}/evidence')
def verification_evidence(ref:str,request:VerificationEvidence,authorization:str|None=Header(default=None)):
    return proxy('POST','/semantic/groups/'+ref+'/evidence',authorization,json=request.model_dump())
