import pytest
from app.runtime.task_runtime import TaskRuntime, TaskRuntimeError
from app.runtime.task_store import InMemoryTaskStore, TaskStoreAccessDenied
from app.schemas.human_handoff import HandoffPrepare, HandoffResult
from app.services.human_handoff_client import HandoffUnavailable

@pytest.fixture(autouse=True)
def no_event_network(monkeypatch):
    from app.services.conversation_state import reset_conversation_state_for_tests
    reset_conversation_state_for_tests()
    monkeypatch.setattr('app.runtime.task_runtime.record_handoff_event',lambda *args:True)

def runtime():
    return TaskRuntime(store=InMemoryTaskStore())

def prepare(r,**kwargs):
    return r.prepare_handoff(HandoffPrepare(session_id='session-a',**kwargs),member_id=1,authorization='Bearer synthetic').view

def confirm(r,view,**kwargs):
    return r.confirm_action(task_ref=view.task_ref,confirmation='confirm',member_id=1,authorization='Bearer synthetic',proposal_ref=view.action.proposal_ref,revision=view.action.revision,**kwargs).view

def test_no_order_no_model_preview_and_reuse():
    r=runtime();a=prepare(r);b=prepare(r)
    assert a.task_ref==b.task_ref and a.action==b.action
    assert a.status=='ready_to_commit' and a.execution_metrics.model_calls==0

def test_confirmation_idempotency_freeze_and_owner(monkeypatch):
    calls=[]
    monkeypatch.setattr('app.runtime.task_runtime.handoff_request',lambda *args,**kw: calls.append(kw) or HandoffResult(caseRef='aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',state='QUEUED',version=1))
    r=runtime();a=prepare(r);assert confirm(r,a).status=='waiting_human'
    assert confirm(r,a).status=='waiting_human' and len(calls)==1
    with pytest.raises(TaskRuntimeError):r.continue_task(task_ref=a.task_ref,message='继续退款',member_id=1,authorization='Bearer synthetic')
    with pytest.raises(TaskRuntimeError):r.confirm_action(task_ref=a.task_ref,confirmation='confirm',member_id=2,authorization='Bearer other',proposal_ref=a.action.proposal_ref,revision=a.action.revision)

def test_revision_and_session_binding():
    r=runtime();a=prepare(r);b=prepare(r,task_ref=a.task_ref,reason='repeated_questions')
    assert b.action.revision==a.action.revision+1
    with pytest.raises(TaskRuntimeError):confirm(r,a)
    with pytest.raises(TaskRuntimeError):r.prepare_handoff(HandoffPrepare(session_id='other',task_ref=a.task_ref),member_id=1,authorization='Bearer synthetic')

def test_unknown_result_is_not_replayed(monkeypatch):
    def fail(*args,**kw):raise HandoffUnavailable()
    monkeypatch.setattr('app.runtime.task_runtime.handoff_request',fail)
    r=runtime();a=prepare(r);b=confirm(r,a)
    assert b.action.confirmation_status=='unknown'
    with pytest.raises(TaskRuntimeError):confirm(r,a)
    with pytest.raises(TaskRuntimeError):r.continue_task(task_ref=a.task_ref,message='继续',member_id=1,authorization='Bearer synthetic')
    monkeypatch.setattr('app.runtime.task_runtime.handoff_request',lambda *a,**kw:HandoffResult(caseRef='aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',state='QUEUED',version=1))
    assert r.reconcile_handoff(task_ref=a.task_ref,member_id=1,authorization='Bearer synthetic').view.status=='waiting_human'

def test_expired_and_withdrawn_never_create(monkeypatch):
    monkeypatch.setattr('app.runtime.task_runtime.handoff_request',lambda *a,**kw:pytest.fail('must not write'))
    r=runtime();a=prepare(r)
    r._now=lambda:10**12
    assert confirm(r,a).status=='blocked'
    r=runtime();a=prepare(r)
    b=r.confirm_action(task_ref=a.task_ref,confirmation='withdraw',member_id=1,authorization='Bearer synthetic',proposal_ref=a.action.proposal_ref,revision=a.action.revision).view
    assert b.action is None

def test_changed_projection_cannot_commit(monkeypatch):
    monkeypatch.setattr('app.runtime.task_runtime.handoff_request',lambda *a,**kw:pytest.fail('must not write'))
    r=runtime();a=prepare(r)
    from app.runtime.task_store import owner_ref_for_member
    bundle=r._store.load_owned(a.task_ref,owner_ref_for_member(1))
    bundle.handoff.reason='business_dispute'
    r._store.save(bundle)
    assert confirm(r,a).status=='blocked'

def test_old_handoff_contract_requires_new_preview(monkeypatch):
    monkeypatch.setattr('app.runtime.task_runtime.handoff_request',lambda *a,**kw:pytest.fail('must not write'))
    r=runtime();a=prepare(r)
    from app.runtime.task_store import owner_ref_for_member
    bundle=r._store.load_owned(a.task_ref,owner_ref_for_member(1));bundle.handoff=None;r._store.save(bundle)
    assert confirm(r,a).status=='blocked'

def test_projection_hash_roundtrip_and_model_cannot_supply_it():
    from app.runtime.task_store import assert_safe_action_arguments,TaskStoreError,TaskRecordBundle,owner_ref_for_member
    with pytest.raises(TaskStoreError):assert_safe_action_arguments({'handoffProjectionHash':'0'*64})
    assert_safe_action_arguments({'handoffProjectionHash':'0'*64},allow_generated_projection_hash=True)
    r=runtime();a=prepare(r)
    bundle=r._store.load_owned(a.task_ref,owner_ref_for_member(1))
    restored=TaskRecordBundle.model_validate_json(bundle.model_dump_json())
    assert restored.handoff==bundle.handoff and restored.action_proposal==bundle.action_proposal

def test_general_preview_can_be_revised_without_starting_another_issue():
    r=runtime();a=prepare(r);b=prepare(r,reason='repeated_questions')
    assert b.task_ref==a.task_ref and b.action.revision==a.action.revision+1
    assert b.handoff_reason=='repeated_questions'

def test_expired_general_preview_can_be_renewed():
    r=runtime();a=prepare(r)
    from app.runtime.task_store import owner_ref_for_member
    bundle=r._store.load_owned(a.task_ref,owner_ref_for_member(1))
    r._now=lambda:bundle.action_proposal.expires_at+1
    b=prepare(r)
    assert b.task_ref==a.task_ref and b.action.revision==a.action.revision+1
    assert b.status=='ready_to_commit'
