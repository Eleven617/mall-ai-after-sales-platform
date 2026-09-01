"""Consent-bound feedback and human-review governance.

This service stores references and synthetic fixtures only.  It intentionally
does not retain customer messages, answers, tokens, order numbers, RAG passages
or runtime trace payloads.  A human reviewer must approve every candidate before
its synthetic EvalCase may join a local regression run.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock

from app.schemas.agent_ops import (
    CustomerFeedbackRequest,
    CustomerFeedbackView,
    FeedbackCandidateCreateRequest,
    FeedbackCandidateView,
)
from app.schemas.quality import EvalCase
from app.services.trace_service import current_correlation_ref


_BEARER_VALUE = re.compile(r"\bbearer\s+\S+", re.IGNORECASE)
_ORDER_LIKE_VALUE = re.compile(r"(?<!\d)\d{10,}(?!\d)")
_PHONE_LIKE_VALUE = re.compile(r"(?<!\d)1\d{10}(?!\d)")
_UNSAFE_KEY_NAMES = {
    "authorization", "token", "member_id", "memberid", "order_sn", "ordersn",
    "phone", "address", "raw_message", "message", "prompt", "rag_context",
    "tool_result", "trace", "trace_id", "service_key", "password",
}


class FeedbackGovernanceError(ValueError):
    pass


@dataclass(frozen=True)
class _ResponseReference:
    response_ref: str
    owner_ref: str
    session_ref: str
    trace_ref: str
    created_at: float


@dataclass(frozen=True)
class _FeedbackRecord:
    view: CustomerFeedbackView
    owner_ref: str
    trace_ref: str


@dataclass(frozen=True)
class _CandidateRecord:
    view: FeedbackCandidateView
    eval_case: EvalCase


class FeedbackGovernanceStore:
    """Small process-local governance store for the local demo/quality page.

    This is deliberately separate from customer/business records.  A process
    restart clears only references and review work, never any Java transaction
    data.  The source-controlled EvalCase suite remains the CI baseline.
    """

    def __init__(self, *, max_records: int = 200, response_ttl_seconds: int = 86_400) -> None:
        self._max_records = max_records
        self._response_ttl_seconds = response_ttl_seconds
        self._responses: OrderedDict[str, _ResponseReference] = OrderedDict()
        self._feedback: OrderedDict[str, _FeedbackRecord] = OrderedDict()
        self._candidates: OrderedDict[str, _CandidateRecord] = OrderedDict()
        self._lock = RLock()

    def register_response(self, *, member_id: int, session_id: str) -> str:
        if not isinstance(member_id, int) or member_id <= 0:
            raise FeedbackGovernanceError("反馈需要已登录的会员上下文。")
        response_ref = str(uuid.uuid4())
        record = _ResponseReference(
            response_ref=response_ref,
            owner_ref=_hash_ref(f"member:{member_id}"),
            session_ref=_hash_ref(f"session:{session_id}"),
            trace_ref=current_correlation_ref(),
            created_at=time.time(),
        )
        with self._lock:
            self._purge_expired_locked()
            self._responses[response_ref] = record
            self._trim_locked(self._responses)
        return response_ref

    def submit_feedback(self, *, member_id: int, request: CustomerFeedbackRequest) -> CustomerFeedbackView:
        owner_ref = _hash_ref(f"member:{member_id}")
        with self._lock:
            self._purge_expired_locked()
            response = self._responses.get(request.response_ref)
            if response is None or response.owner_ref != owner_ref:
                raise FeedbackGovernanceError("该反馈引用不存在、已过期或不属于当前会员。")
            existing = next(
                (
                    record.view
                    for record in self._feedback.values()
                    if record.view.response_ref == request.response_ref and record.owner_ref == owner_ref
                ),
                None,
            )
            if existing is not None:
                return existing
            view = CustomerFeedbackView(
                feedback_id=str(uuid.uuid4()),
                response_ref=request.response_ref,
                helpful=request.helpful,
                reason_code=request.reason_code,
                review_status="PENDING",
                created_at=datetime.now(timezone.utc),
            )
            self._feedback[view.feedback_id] = _FeedbackRecord(
                view=view,
                owner_ref=owner_ref,
                trace_ref=response.trace_ref,
            )
            self._trim_locked(self._feedback)
            return view

    def create_candidate(self, request: FeedbackCandidateCreateRequest) -> FeedbackCandidateView:
        _assert_safe_synthetic_value(request.sanitized_scenario)
        _assert_safe_synthetic_value(request.eval_case.model_dump(mode="json"))
        if request.eval_case.synthetic_input != request.sanitized_scenario:
            raise FeedbackGovernanceError("评测案例输入必须等于已脱敏的场景摘要。")
        with self._lock:
            if request.feedback_id not in self._feedback:
                raise FeedbackGovernanceError("反馈记录不存在，不能创建评测候选。")
            if any(record.view.feedback_id == request.feedback_id for record in self._candidates.values()):
                raise FeedbackGovernanceError("该反馈已存在待审核的评测候选。")
            view = FeedbackCandidateView(
                candidate_id=str(uuid.uuid4()),
                feedback_id=request.feedback_id,
                target_agent=request.eval_case.target_agent,
                sanitized_scenario=request.sanitized_scenario,
                review_status="PENDING",
                created_at=datetime.now(timezone.utc),
            )
            self._candidates[view.candidate_id] = _CandidateRecord(view=view, eval_case=request.eval_case)
            self._trim_locked(self._candidates)
            return view

    def approve_candidate(self, candidate_id: str) -> FeedbackCandidateView:
        with self._lock:
            record = self._candidates.get(candidate_id)
            if record is None:
                raise FeedbackGovernanceError("反馈候选不存在。")
            if record.view.review_status == "APPROVED":
                return record.view
            updated = record.view.model_copy(
                update={
                    "review_status": "APPROVED",
                    "eval_case_id": record.eval_case.case_id,
                    "reviewed_at": datetime.now(timezone.utc),
                }
            )
            self._candidates[candidate_id] = _CandidateRecord(view=updated, eval_case=record.eval_case)
            return updated

    def reject_candidate(self, candidate_id: str) -> FeedbackCandidateView:
        with self._lock:
            record = self._candidates.get(candidate_id)
            if record is None:
                raise FeedbackGovernanceError("反馈候选不存在。")
            updated = record.view.model_copy(
                update={"review_status": "REJECTED", "reviewed_at": datetime.now(timezone.utc)}
            )
            self._candidates[candidate_id] = _CandidateRecord(view=updated, eval_case=record.eval_case)
            return updated

    def list_candidates(self) -> list[FeedbackCandidateView]:
        with self._lock:
            return [record.view for record in reversed(self._candidates.values())]

    def approved_eval_cases(self) -> list[EvalCase]:
        with self._lock:
            return [
                record.eval_case
                for record in self._candidates.values()
                if record.view.review_status == "APPROVED"
            ]

    def delete_session_data(self, *, member_id: int, session_id: str) -> dict[str, int]:
        """Delete the local, consent-bound feedback chain for one chat session.

        The process-local store contains only opaque references plus fully
        synthetic candidate data.  Removing a customer conversation removes
        all response references, feedback records and candidate-review work
        derived from that session, including approved-but-not-source-controlled
        cases.  A separately committed repository EvalCase has no feedback or
        session reference and is deliberately outside this deletion boundary.
        """

        if not isinstance(member_id, int) or member_id <= 0:
            raise FeedbackGovernanceError("删除反馈关联需要已登录的会员上下文。")
        owner_ref = _hash_ref(f"member:{member_id}")
        session_ref = _hash_ref(f"session:{session_id}")
        with self._lock:
            response_refs = {
                ref
                for ref, record in self._responses.items()
                if record.owner_ref == owner_ref and record.session_ref == session_ref
            }
            feedback_ids = {
                feedback_id
                for feedback_id, record in self._feedback.items()
                if record.owner_ref == owner_ref and record.view.response_ref in response_refs
            }
            for ref in response_refs:
                self._responses.pop(ref, None)
            for feedback_id in feedback_ids:
                self._feedback.pop(feedback_id, None)
            candidate_ids = {
                candidate_id
                for candidate_id, record in self._candidates.items()
                if record.view.feedback_id in feedback_ids
            }
            for candidate_id in candidate_ids:
                self._candidates.pop(candidate_id, None)
        return {
            "responses": len(response_refs),
            "feedback": len(feedback_ids),
            "candidates": len(candidate_ids),
        }

    def _purge_expired_locked(self) -> None:
        cutoff = time.time() - self._response_ttl_seconds
        for ref, record in list(self._responses.items()):
            if record.created_at < cutoff:
                self._responses.pop(ref, None)

    def _trim_locked(self, records: OrderedDict) -> None:
        while len(records) > self._max_records:
            records.popitem(last=False)


def _hash_ref(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _assert_safe_synthetic_value(value: object) -> None:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if _BEARER_VALUE.search(serialized) or _ORDER_LIKE_VALUE.search(serialized) or _PHONE_LIKE_VALUE.search(serialized):
        raise FeedbackGovernanceError("评测候选只能包含虚构、脱敏的合成数据。")
    _assert_safe_keys(value)


def _assert_safe_keys(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in _UNSAFE_KEY_NAMES:
                raise FeedbackGovernanceError("评测候选包含不允许的敏感字段。")
            _assert_safe_keys(item)
    elif isinstance(value, list):
        for item in value:
            _assert_safe_keys(item)


feedback_governance_store = FeedbackGovernanceStore()
