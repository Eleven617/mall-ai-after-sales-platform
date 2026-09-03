"""Customer-facing Agent Task Runtime API.

The API exposes only safe task summaries and events. Internal task IDs,
argument vaults, complete business identifiers, prompts and raw tool results
remain server-side.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse

from app.schemas.agent_task import (
    AgentTaskConfirmationRequest,
    AgentTaskCreateRequest,
    AgentTaskEvent,
    AgentTaskPublicView,
    AgentTaskContinueRequest,
)
from app.runtime.task_runtime import (
    TaskRuntimeError,
    get_task_runtime,
)
from app.services.mall_client import MallAuthenticationError, get_current_member


router = APIRouter(prefix="/agent-tasks", tags=["agent-tasks"])


def _member(authorization: str | None):
    try:
        return get_current_member(authorization)
    except MallAuthenticationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


def _handle_runtime_error(exc: TaskRuntimeError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("", response_model=AgentTaskPublicView, status_code=201)
def create_agent_task(
    request: AgentTaskCreateRequest,
    authorization: str | None = Header(default=None),
) -> AgentTaskPublicView:
    member = _member(authorization)
    try:
        result = get_task_runtime().create_task(
            session_id=request.session_id,
            goal=request.goal,
            success_criteria=request.success_criteria,
            member_id=member.member_id,
            authorization=authorization,
        )
        return result.view
    except TaskRuntimeError as exc:
        _handle_runtime_error(exc)


@router.get("", response_model=list[AgentTaskPublicView])
def list_agent_tasks(
    session_id: str | None = None,
    authorization: str | None = Header(default=None),
) -> list[AgentTaskPublicView]:
    member = _member(authorization)
    try:
        return get_task_runtime().list_tasks(
            session_id=session_id,
            member_id=member.member_id,
            authorization=authorization,
        )
    except TaskRuntimeError as exc:
        _handle_runtime_error(exc)


@router.get("/{task_ref}", response_model=AgentTaskPublicView)
def get_agent_task(
    task_ref: str,
    authorization: str | None = Header(default=None),
) -> AgentTaskPublicView:
    member = _member(authorization)
    try:
        return get_task_runtime().get_task(
            task_ref=task_ref,
            member_id=member.member_id,
            authorization=authorization,
        )
    except TaskRuntimeError as exc:
        _handle_runtime_error(exc)


@router.post("/{task_ref}/messages", response_model=AgentTaskPublicView)
def continue_agent_task(
    task_ref: str,
    request: AgentTaskContinueRequest,
    authorization: str | None = Header(default=None),
) -> AgentTaskPublicView:
    member = _member(authorization)
    try:
        return get_task_runtime().continue_task(
            task_ref=task_ref,
            message=request.message,
            member_id=member.member_id,
            authorization=authorization,
        ).view
    except TaskRuntimeError as exc:
        _handle_runtime_error(exc)


@router.post("/{task_ref}/action", response_model=AgentTaskPublicView)
def confirm_agent_task_action(
    task_ref: str,
    request: AgentTaskConfirmationRequest,
    authorization: str | None = Header(default=None),
) -> AgentTaskPublicView:
    member = _member(authorization)
    try:
        return get_task_runtime().confirm_action(
            task_ref=task_ref,
            confirmation=request.confirmation,
            member_id=member.member_id,
            authorization=authorization,
        ).view
    except TaskRuntimeError as exc:
        _handle_runtime_error(exc)


@router.get("/{task_ref}/events", response_model=list[AgentTaskEvent])
def list_agent_task_events(
    task_ref: str,
    authorization: str | None = Header(default=None),
) -> list[AgentTaskEvent]:
    member = _member(authorization)
    try:
        return get_task_runtime().list_events(
            task_ref=task_ref,
            member_id=member.member_id,
            authorization=authorization,
        )
    except TaskRuntimeError as exc:
        _handle_runtime_error(exc)


@router.get("/{task_ref}/events/stream")
def stream_agent_task_events(
    task_ref: str,
    authorization: str | None = Header(default=None),
) -> StreamingResponse:
    """Return a finite safe SSE snapshot; clients can reconnect/poll."""

    member = _member(authorization)
    try:
        events = get_task_runtime().list_events(
            task_ref=task_ref,
            member_id=member.member_id,
            authorization=authorization,
        )
    except TaskRuntimeError as exc:
        _handle_runtime_error(exc)

    def body():
        for event in events:
            yield f"event: {event.event_type}\ndata: {json.dumps(event.model_dump(mode='json'), ensure_ascii=False)}\n\n"

    return StreamingResponse(body(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
