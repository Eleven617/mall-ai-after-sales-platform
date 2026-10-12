import math
import pytest
from app.services.handoff_projection import project,semantic_text
from app.services.handoff_semantic import normalize,rank
from app.services.handoff_semantic_worker import validate_draft

def test_projection_keeps_obstacle_not_customer_text():
    value=project('exchange','这款耳机换货不知道需要哪些材料，帮我转人工')
    assert value['content_quality']=='READY'
    assert value['unresolved_question']=='材料要求不清楚'
    assert '耳机' not in str(value)
    assert '材料' in semantic_text(value,'exchange')

@pytest.mark.parametrize('text',['电话19900000000，需要材料','密码secret，请转人工','住址某某街道，凭证怎么办'])
def test_sensitive_description_falls_back_without_copy(text):
    value=project('exchange',text)
    assert value['content_quality']=='REDACTION_REJECTED'
    assert not value['issue_codes'] and not value['unresolved_question']
    assert text not in str(value)

@pytest.mark.parametrize('text',['','转人工','想换货','材料已经明白了','如果材料不清楚怎么办','不是入口的问题'])
def test_insufficient_content_never_embedded(text):
    value=project('exchange',text)
    assert value['content_quality']=='INSUFFICIENT_CONTEXT'
    with pytest.raises(ValueError):semantic_text(value,'exchange')

def test_multi_issue_is_explicit_not_one_invented_root_cause():
    value=project('exchange','材料不明白，而且找不到入口')
    assert value['issue_codes']==['materials','entry']
    assert value['verified_fact_codes']==[]

def test_exact_rank_normalization_ties_and_scope():
    assert rank([2,0],{'b':[1,0],'a':[10,0],'c':[0,1]},2,2)==[('a',1.0),('b',1.0)]
    with pytest.raises(ValueError):rank([1,0],{},21,2)
    with pytest.raises(ValueError):rank([1,0],{str(i):[1,0] for i in range(5001)},5,2)

@pytest.mark.parametrize('value',[[0,0],[math.inf,0],[math.nan,1],[1]])
def test_invalid_vectors_rejected(value):
    with pytest.raises(ValueError):normalize(value,2)

def test_draft_references_and_privacy():
    snapshot={'samples':[{'caseRef':'safe-case'}]}
    draft={'shared_issue':'换货材料要求不清楚','evidence_refs':['safe-case'],'hypotheses':[],
           'suggested_actions':[{'action':'检查材料说明','verification':'人工检查说明是否覆盖凭证类型'}],
           'limitations':'仅依据有限样例，客户陈述尚未核实。'}
    assert validate_draft(draft,snapshot)==draft
    with pytest.raises(ValueError):validate_draft({**draft,'evidence_refs':['foreign']},snapshot)
    with pytest.raises(ValueError):validate_draft({**draft,'shared_issue':'电话19900000000'},snapshot)

def test_preview_revision_binds_semantic_projection(monkeypatch):
    from app.services.conversation_state import reset_conversation_state_for_tests
    reset_conversation_state_for_tests()
    from app.runtime.task_runtime import TaskRuntime
    from app.runtime.task_store import InMemoryTaskStore
    from app.schemas.human_handoff import HandoffPrepare
    monkeypatch.setattr('app.runtime.task_runtime.record_handoff_event',lambda *a:True)
    runtime=TaskRuntime(store=InMemoryTaskStore())
    def prepare(text):return runtime.prepare_handoff(HandoffPrepare(session_id='safe-session',topic='exchange',problem_description=text),member_id=1,authorization='Bearer synthetic').view
    first=prepare('换货材料不清楚');second=prepare('换货入口在哪里')
    assert first.task_ref==second.task_ref
    assert first.handoff_problem['projection_hash']!=second.handoff_problem['projection_hash']
    assert second.action.revision==first.action.revision+1
    assert second.handoff_problem['unresolved_question']=='找不到办理入口'
