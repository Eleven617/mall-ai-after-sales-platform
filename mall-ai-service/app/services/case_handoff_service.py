"""Customer-diagnosis to Java handoff boundary.

Only a previously produced, server-side DiagnosisHandoff is converted to this
contract. Raw customer text and the handoff summary never cross the boundary.
"""

import hashlib

import httpx

from app.config import settings
from app.services.request_context import correlation_headers
from app.schemas.diagnosis import DiagnosisResult
from app.schemas.operations import CaseHandoffView


class CaseHandoffError(RuntimeError):
    """The durable Java handoff could not be confirmed."""


def register_case_handoff(
    *,
    session_id: str,
    diagnosis: DiagnosisResult,
    authorization: str | None,
) -> CaseHandoffView:
    if not authorization or not authorization.startswith("Bearer "):
        raise CaseHandoffError("当前无法登记人工跟进，请登录后重试或联系客服。")
    if diagnosis.handoff is None:
        raise CaseHandoffError("当前没有可登记的人工跟进事项。")

    request_payload = {
        "caseKey": _build_case_key(session_id, diagnosis),
        "sourceFlow": "customer_diagnosis",
        "diagnosisCategory": diagnosis.category,
        "evidenceStatus": diagnosis.evidence_status,
        "handoffReason": diagnosis.handoff.reason,
        "requiresHumanReview": True,
        "schemaVersion": "1",
    }
    url = f"{settings.mall_api_base_url.rstrip('/')}/ai/cases/handoffs"
    try:
        response = httpx.post(
            url,
            headers={
                "Authorization": authorization,
                "X-AI-Handoff-Key": settings.ai_case_handoff_service_key,
                **correlation_headers(),
            },
            json=request_payload,
            timeout=settings.mall_api_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise CaseHandoffError("当前无法登记人工跟进，请稍后重试或联系客服。") from exc

    if response.status_code in {401, 403}:
        raise CaseHandoffError("当前无法登记人工跟进，请重新登录或联系客服。")
    if response.status_code >= 500:
        raise CaseHandoffError("当前无法登记人工跟进，请稍后重试或联系客服。")
    try:
        payload = response.json()
    except ValueError as exc:
        raise CaseHandoffError("人工跟进登记结果无法确认，请稍后查询。") from exc
    if response.status_code >= 400 or not isinstance(payload, dict) or payload.get("code") != 200:
        raise CaseHandoffError("当前无法登记人工跟进，请稍后重试或联系客服。")
    try:
        return CaseHandoffView.model_validate(payload.get("data"), extra="forbid")
    except Exception as exc:
        raise CaseHandoffError("人工跟进登记结果无法确认，请稍后查询。") from exc


def _build_case_key(session_id: str, diagnosis: DiagnosisResult) -> str:
    handoff_reason = diagnosis.handoff.reason if diagnosis.handoff else "none"
    canonical = "\0".join(
        ("build19", session_id, diagnosis.category, diagnosis.evidence_status, handoff_reason)
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
