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
