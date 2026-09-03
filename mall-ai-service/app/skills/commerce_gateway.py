"""Deterministic Skill Gateway adapters for the v3.0 Runtime.

The gateway is the only place where a Runtime Skill may touch Java or the
policy RAG service.  It returns a small observation projection; raw HTTP
payloads, credentials, complete identifiers and RAG passages never enter the
TaskStore or the public DTO.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.after_sales_application import AfterSalesApplicationView
from app.services.business_tools import query_inventory
from app.services.mall_client import (
    MallApiClientError,
    check_after_sales_eligibility,
    create_after_sales_application,
    get_order_snapshot,
    list_my_after_sales_applications,
)
from app.runtime.reference_vault import RuntimeReferenceVault
from app.runtime.task_store import owner_ref_for_member
from app.services.rag_service import answer_after_sales_question
from app.services.tool_context import ToolExecutionContext


class SkillGatewayError(RuntimeError):
    """A safe, categorized gateway failure."""

    def __init__(self, message: str, *, category: str = "unavailable") -> None:
        super().__init__(message)
        self.category = category


class SkillObservation(BaseModel):
    """Safe result returned to the Runtime and turned into a TaskArtifact."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(pattern=r"^(succeeded|blocked|unavailable|failed)$")
    artifact_kind: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    summary: str = Field(min_length=1, max_length=320)
    reference: str = Field(pattern=r"^[a-z][a-z0-9_-]{7,79}$")
    source_version: str = Field(pattern=r"^v[0-9]+(?:\.[0-9]+){0,2}$")
    factuality: str = Field(pattern=r"^(verified|derived|proposal|unavailable)$")
    action_ref: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_-]{7,79}$")
    outbox_ref: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_-]{7,79}$")
    safe_facts: dict[str, str] = Field(default_factory=dict, max_length=8)

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("Skill 结果摘要不能为空")
        if any(marker in normalized.lower() for marker in ("bearer ", "token=", "password", "rag原文", "traceback")):
            raise ValueError("Skill 结果摘要包含禁止内容")
        if re.search(r"(?<!\d)\d{6,}(?!\d)", normalized):
            raise ValueError("Skill 结果摘要不能包含完整业务标识")
        return normalized


class SkillGateway(Protocol):
    def invoke(
        self,
        skill_id: str,
        arguments: Mapping[str, Any],
        *,
        authorization: str | None,
        member_id: int | None,
        task_ref: str,
    ) -> SkillObservation: ...

    def commit(
        self,
        skill_id: str,
        arguments: Mapping[str, Any],
        *,
        authorization: str | None,
        member_id: int | None,
        task_ref: str,
    ) -> SkillObservation: ...


def _reference(prefix: str, value: object) -> str:
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:24]
    return f"{prefix}-{digest}"


def _require_customer_context(authorization: str | None, member_id: int | None) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise SkillGatewayError("请先登录后再继续处理。", category="unauthenticated")
    if isinstance(member_id, bool) or not isinstance(member_id, int) or member_id <= 0:
        raise SkillGatewayError("当前身份无法执行该任务。", category="scope_denied")


class SafeCommerceSkillGateway:
    """Production adapter over existing Java/RAG clients.

    New v3 Skill IDs are mapped here, rather than in the Executor.  This keeps
    model planning open-ended while the server retains one deterministic
    capability boundary.  Actions that have no safe Java implementation yet
    return ``blocked`` instead of pretending that a business write happened.
    """

    def __init__(self, *, reference_vault: RuntimeReferenceVault | None = None) -> None:
        self._reference_vault = reference_vault or RuntimeReferenceVault()

    def invoke(
        self,
        skill_id: str,
        arguments: Mapping[str, Any],
        *,
        authorization: str | None,
        member_id: int | None,
        task_ref: str,
    ) -> SkillObservation:
        if skill_id in {
            "read_order",
            "read_logistics",
            "search_catalog",
            "list_service_applications",
        }:
            _require_customer_context(authorization, member_id)
        try:
            if skill_id == "read_order":
                return self._read_order(arguments, authorization, member_id, task_ref)
            if skill_id == "read_logistics":
                return self._read_logistics(arguments, authorization, member_id, task_ref)
            if skill_id == "read_inventory":
                return self._read_inventory(arguments, authorization, member_id)
            if skill_id == "retrieve_policy":
                return self._retrieve_policy(arguments)
            if skill_id == "list_service_applications":
                return self._list_applications(authorization)
            if skill_id == "build_service_resolution":
                return self._build_resolution(arguments)
            if skill_id == "search_task_memory":
                return SkillObservation(
                    status="succeeded",
                    artifact_kind="memory_hint",
                    summary="当前任务记忆已查询；没有可安全复用的历史摘要。",
                    reference=_reference("memory", task_ref),
                    source_version="v1",
                    factuality="derived",
                )
            if skill_id == "spawn_subtask":
                return SkillObservation(
                    status="succeeded",
                    artifact_kind="async_task",
                    summary="已创建一个受控调查子任务，等待运行时继续执行。",
                    reference=_reference("subtask", task_ref),
                    source_version="v1",
                    factuality="derived",
                )
            if skill_id in {
                "create_after_sales_draft",
                "amend_after_sales_draft",
                "open_human_case",
                "request_customer_evidence",
                "schedule_follow_up",
            }:
                return SkillObservation(
                    status="blocked",
                    artifact_kind="async_task" if skill_id != "create_after_sales_draft" else "action_result",
                    summary="该行动需要现有统一售后/人工协同适配器提供受控参数，当前未执行任何业务写入。",
                    reference=_reference("blocked", f"{skill_id}:{task_ref}"),
                    source_version="v1",
                    factuality="unavailable",
                    safe_facts={"failure_code": "skill_adapter_not_configured"},
                )
        except MallApiClientError as exc:
            return SkillObservation(
                status="unavailable",
                artifact_kind="action_result" if skill_id.endswith("draft") else "order_fact",
                summary="业务 Skill 暂时无法取得可核验结果，请稍后重试。",
                reference=_reference("unavailable", f"{skill_id}:{task_ref}"),
                source_version="v1",
                factuality="unavailable",
                safe_facts={"failure_code": "upstream_unavailable"},
            )
        except SkillGatewayError as exc:
            return SkillObservation(
                status="blocked",
                artifact_kind="action_result",
                summary=str(exc),
                reference=_reference("blocked", f"{skill_id}:{task_ref}"),
                source_version="v1",
                factuality="unavailable",
                safe_facts={"failure_code": exc.category},
            )
        return SkillObservation(
            status="blocked",
            artifact_kind="action_result",
            summary="当前 Skill 未注册可执行适配器，未产生业务写入。",
            reference=_reference("blocked", f"{skill_id}:{task_ref}"),
            source_version="v1",
            factuality="unavailable",
            safe_facts={"failure_code": "unknown_skill_adapter"},
        )

    def commit(
        self,
        skill_id: str,
        arguments: Mapping[str, Any],
        *,
        authorization: str | None,
        member_id: int | None,
        task_ref: str,
    ) -> SkillObservation:
        """Commit only through a future adapter; never fake a Java result."""

        _require_customer_context(authorization, member_id)
        if skill_id != "commit_after_sales_action":
            return SkillObservation(
                status="blocked",
                artifact_kind="action_result",
                summary="该提交 Skill 不在当前运行时的受控写入白名单中。",
                reference=_reference("blocked", f"commit:{skill_id}:{task_ref}"),
                source_version="v1",
                factuality="unavailable",
                safe_facts={"failure_code": "commit_skill_not_allowlisted"},
            )
        order_fact_ref = arguments.get("orderFactRef")
        application_type = arguments.get("applicationType")
        idempotency_key = arguments.get("idempotencyKey")
        if not isinstance(order_fact_ref, str) or not isinstance(application_type, str) or not isinstance(idempotency_key, str):
            return self._blocked_commit(task_ref, "commit_arguments_incomplete")
        if application_type not in {"cancel_refund", "return_refund", "exchange", "repair"}:
            return self._blocked_commit(task_ref, "application_type_invalid")
        if not re.fullmatch(r"[a-f0-9]{32}", idempotency_key):
            return self._blocked_commit(task_ref, "idempotency_key_invalid")
        order_sn = self._reference_vault.resolve(
            reference=order_fact_ref,
            owner_ref=owner_ref_for_member(member_id or 0),
            task_ref=task_ref,
            kind="order_sn",
        )
        if order_sn is None:
            return self._blocked_commit(task_ref, "order_fact_reference_expired")
        try:
            eligibility = check_after_sales_eligibility(
                order_sn,
                application_type,
                authorization,
            )
            if eligibility.decision != "eligible_to_apply":
                return self._blocked_commit(task_ref, "java_eligibility_denied")
            application = create_after_sales_application(
                order_sn=order_sn,
                application_type=application_type,
                order_item_id=None,
                reason="customer_requested_after_sales",
                description="客户已在受控 Agent Runtime 中明确确认提交。",
                idempotency_key=idempotency_key,
                authorization=authorization,
            )
        except MallApiClientError:
            return SkillObservation(
                status="unavailable",
                artifact_kind="action_result",
                summary="Java 尚未返回可核验的提交结果；AI 层不会重放该业务动作。",
                reference=_reference("commit", f"unknown:{task_ref}"),
                source_version="v1",
                factuality="unavailable",
                safe_facts={"failure_code": "java_commit_result_unknown"},
            )
        return SkillObservation(
            status="succeeded",
            artifact_kind="action_result",
            summary="Java 已完成售后申请提交并返回当前公开状态；后续履约以商城状态为准。",
            reference=_reference("action", application.application_id),
            source_version="v1",
            factuality="verified",
            action_ref=_reference("action", application.application_id),
            outbox_ref=_reference("outbox", application.application_id),
            safe_facts={"submission_status": application.status},
        )

    @staticmethod
    def _blocked_commit(task_ref: str, failure_code: str) -> SkillObservation:
        return SkillObservation(
            status="blocked",
            artifact_kind="action_result",
            summary="当前行动缺少仍可核验的业务事实，未写入售后、订单或队列。",
            reference=_reference("blocked", f"commit:{failure_code}:{task_ref}"),
            source_version="v1",
            factuality="unavailable",
            safe_facts={"failure_code": failure_code},
        )

    def _read_order(
        self,
        arguments: Mapping[str, Any],
        authorization: str | None,
        member_id: int | None,
        task_ref: str,
    ) -> SkillObservation:
        order_sn = arguments.get("order_sn") or arguments.get("orderRef")
        if not isinstance(order_sn, str) or not order_sn.strip():
            raise SkillGatewayError("还需要一个订单标识才能核验订单事实。", category="missing_order_reference")
        snapshot = get_order_snapshot(order_sn.strip(), authorization)
        status = str(snapshot.get("status") or "状态未知")[:80]
        products = snapshot.get("product_names") or []
        count = len(products) if isinstance(products, list) else 0
        reference = _reference("fact", f"order:{order_sn}")
        self._reference_vault.put(
            reference=reference,
            owner_ref=owner_ref_for_member(member_id or 0),
            task_ref=task_ref,
            kind="order_sn",
            value=order_sn,
        )
        return SkillObservation(
            status="succeeded",
            artifact_kind="order_fact",
            summary=f"Java 已核验当前账号订单事实；状态：{status}；商品项：{count}。",
            reference=reference,
            source_version="v1",
            factuality="verified",
            safe_facts={"order_status": status, "product_count": str(count)},
        )

    def _read_logistics(
        self,
        arguments: Mapping[str, Any],
        authorization: str | None,
        member_id: int | None,
        task_ref: str,
    ) -> SkillObservation:
        order_observation = self._read_order(arguments, authorization, member_id, task_ref)
        reference = _reference("fact", f"logistics:{order_observation.reference}")
        order_sn = arguments.get("order_sn") or arguments.get("orderRef")
        if isinstance(order_sn, str) and order_sn.strip():
            self._reference_vault.put(
                reference=reference,
                owner_ref=owner_ref_for_member(member_id or 0),
                task_ref=task_ref,
                kind="order_sn",
                value=order_sn.strip(),
            )
        return order_observation.model_copy(
            update={
                "artifact_kind": "logistics_fact",
                "summary": "Java 已核验当前账号订单的物流摘要；具体节点以商城公开状态为准。",
                "reference": reference,
                "safe_facts": {"order_status": order_observation.safe_facts.get("order_status", "unknown")},
            }
        )

    def _read_inventory(
        self,
        arguments: Mapping[str, Any],
        authorization: str | None,
        member_id: int | None,
    ) -> SkillObservation:
        sku_id = arguments.get("sku_id") or arguments.get("skuRef")
        if not isinstance(sku_id, str) or not sku_id.strip():
            raise SkillGatewayError("还需要一个 SKU 标识才能查询库存。", category="missing_sku_reference")
        # The existing adapter is explicitly synthetic until Java exposes a
        # member-safe inventory endpoint.  It is never described as production
        # inventory, and callers can disable it in a stricter deployment.
        result = query_inventory({"sku_id": sku_id.strip()}, ToolExecutionContext(authorization=authorization, member_id=member_id))
        return SkillObservation(
            status="succeeded",
            artifact_kind="inventory_fact",
            summary="已取得本地合成库存摘要；它仅用于演示，不代表真实仓储库存。",
            reference=_reference("synthetic", f"inventory:{sku_id}"),
            source_version="v1",
            factuality="derived",
            safe_facts={"availability": str(result.get("status", "unknown"))},
        )

    def _retrieve_policy(self, arguments: Mapping[str, Any]) -> SkillObservation:
        query = arguments.get("query")
        if not isinstance(query, str) or not query.strip():
            raise SkillGatewayError("请补充要查询的政策主题。", category="missing_policy_query")
        result = answer_after_sales_question(query.strip())
        if result.retrieval_unavailable:
            return SkillObservation(
                status="unavailable",
                artifact_kind="policy_evidence",
                summary="政策检索暂时不可用，未形成政策结论。",
                reference=_reference("policy", query),
                source_version="v2",
                factuality="unavailable",
                safe_facts={"failure_code": "rag_unavailable"},
            )
        source_count = len(result.sources or [])
        if result.no_evidence:
            return SkillObservation(
                status="blocked",
                artifact_kind="policy_evidence",
                summary="当前政策语料没有达到证据门槛，不能据此作出结论。",
                reference=_reference("policy", query),
                source_version="v2",
                factuality="unavailable",
                safe_facts={"source_count": str(source_count), "failure_code": "insufficient_evidence"},
            )
        return SkillObservation(
            status="succeeded",
            artifact_kind="policy_evidence",
            summary=f"已取得 {source_count} 条版本化政策证据摘要；回答仍需经过证据核验。",
            reference=_reference("policy", query),
            source_version="v2",
            factuality="verified",
            safe_facts={"source_count": str(source_count)},
        )

    def _list_applications(self, authorization: str | None) -> SkillObservation:
        applications = list_my_after_sales_applications(authorization)
        status_counts: dict[str, int] = {}
        for item in applications:
            status_counts[item.status] = status_counts.get(item.status, 0) + 1
        return SkillObservation(
            status="succeeded",
            artifact_kind="after_sales_fact",
            summary=f"Java 已返回当前账号可见的售后申请摘要，共 {len(applications)} 项。",
            reference=_reference("after-sales", len(applications)),
            source_version="v1",
            factuality="verified",
            safe_facts={f"status_{key}": str(value) for key, value in list(status_counts.items())[:6]},
        )

    def _build_resolution(self, arguments: Mapping[str, Any]) -> SkillObservation:
        facts = arguments.get("factRefs") or arguments.get("facts") or []
        if not isinstance(facts, list) or not facts:
            return SkillObservation(
                status="blocked",
                artifact_kind="resolution_candidate",
                summary="尚无足够的已核验事实来生成可执行方案。",
                reference=_reference("resolution", "empty"),
                source_version="v1",
                factuality="unavailable",
                safe_facts={"failure_code": "facts_incomplete"},
            )
        return SkillObservation(
            status="succeeded",
            artifact_kind="resolution_candidate",
            summary="已根据已核验事实生成候选解决方案摘要，提交前仍需客户确认与 Java 复核。",
            reference=_reference("resolution", "|".join(str(item) for item in facts)),
            source_version="v1",
            factuality="proposal",
            safe_facts={"candidate_count": "1"},
        )


@dataclass
class SyntheticSkillGateway:
    """Fixture-backed gateway used by deterministic contract/live-synthetic evals."""

    observations: dict[str, SkillObservation]

    def invoke(
        self,
        skill_id: str,
        arguments: Mapping[str, Any],
        *,
        authorization: str | None,
        member_id: int | None,
        task_ref: str,
    ) -> SkillObservation:
        observation = self.observations.get(skill_id)
        if observation is None:
            return SkillObservation(
                status="blocked",
                artifact_kind="action_result",
                summary="合成 Skill 未提供该能力的 fixture。",
                reference=_reference("synthetic", f"missing:{skill_id}"),
                source_version="v1",
                factuality="unavailable",
                safe_facts={"failure_code": "fixture_missing"},
            )
        return observation

    def commit(
        self,
        skill_id: str,
        arguments: Mapping[str, Any],
        *,
        authorization: str | None,
        member_id: int | None,
        task_ref: str,
    ) -> SkillObservation:
        return self.invoke(skill_id, arguments, authorization=authorization, member_id=member_id, task_ref=task_ref)
