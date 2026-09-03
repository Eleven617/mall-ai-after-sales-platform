"""The single allow-listed Skill Catalog for the E-Commerce Task Runtime."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


SKILL_CATALOG_VERSION = "skill_catalog_v3_0"
SkillDomain = Literal[
    "catalog",
    "order",
    "fulfillment",
    "inventory",
    "knowledge",
    "after_sales",
    "collaboration",
    "runtime",
]
SkillActionMode = Literal["read", "draft", "commit", "async_task"]


class SkillDefinition(BaseModel):
    """Metadata shown to the Executor after deterministic discovery."""

    model_config = ConfigDict(extra="forbid")

    skill_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    semantic_version: str = Field(pattern=r"^v[0-9]+(?:\.[0-9]+){0,2}$")
    domain: SkillDomain
    description: str = Field(min_length=1, max_length=240)
    input_schema_ref: str = Field(pattern=r"^schemas/skills/[a-z0-9_.-]+\.input\.json$")
    output_schema_ref: str = Field(pattern=r"^schemas/skills/[a-z0-9_.-]+\.output\.json$")
    action_mode: SkillActionMode
    estimated_latency_ms: int = Field(ge=0, le=120_000)
    estimated_model_cost: str = Field(min_length=1, max_length=40)
    artifact_kinds: list[str] = Field(default_factory=list, max_length=4)
    examples: list[str] = Field(default_factory=list, max_length=4)
    discovery_terms: list[str] = Field(default_factory=list, max_length=8)
    allowed_roles: tuple[Literal["customer", "quality_evaluation"] , ...] = ("customer",)
    requires_confirmation: bool = False
    max_calls_per_task: int = Field(default=2, ge=1, le=8)

    @field_validator("artifact_kinds")
    @classmethod
    def validate_artifact_kinds(cls, values: list[str]) -> list[str]:
        for value in values:
            if not isinstance(value, str) or not value or len(value) > 64:
                raise ValueError("artifact kind 不合法")
        return values

    @field_validator("discovery_terms")
    @classmethod
    def validate_discovery_terms(cls, values: list[str]) -> list[str]:
        for value in values:
            if not isinstance(value, str) or not value.strip() or len(value) > 32:
                raise ValueError("discovery term 不合法")
        return values


_CATALOG: tuple[SkillDefinition, ...] = (
    SkillDefinition(
        skill_id="search_catalog",
        semantic_version="v1",
        domain="catalog",
        description="按用户需求搜索当前可见商品和规格摘要",
        input_schema_ref="schemas/skills/search_catalog.input.json",
        output_schema_ref="schemas/skills/search_catalog.output.json",
        action_mode="read",
        estimated_latency_ms=300,
        estimated_model_cost="none",
        artifact_kinds=["catalog_fact"],
        examples=["寻找适合出差使用的降噪耳机"],
        discovery_terms=["商品", "规格", "搜索", "推荐"],
    ),
    SkillDefinition(
        skill_id="compare_skus",
        semantic_version="v1",
        domain="catalog",
        description="对服务端提供的商品候选形成规格对比事实",
        input_schema_ref="schemas/skills/compare_skus.input.json",
        output_schema_ref="schemas/skills/compare_skus.output.json",
        action_mode="read",
        estimated_latency_ms=350,
        estimated_model_cost="none",
        artifact_kinds=["sku_comparison"],
        examples=["比较两个候选耳机的可见规格"],
        discovery_terms=["比较", "对比", "规格", "SKU"],
    ),
    SkillDefinition(
        skill_id="read_order",
        semantic_version="v1",
        domain="order",
        description="读取当前登录用户可访问订单的履约摘要",
        input_schema_ref="schemas/skills/read_order.input.json",
        output_schema_ref="schemas/skills/read_order.output.json",
        action_mode="read",
        estimated_latency_ms=300,
        estimated_model_cost="none",
        artifact_kinds=["order_fact"],
        examples=["核对一笔订单的当前状态"],
        discovery_terms=["订单", "订单状态", "履约"],
    ),
    SkillDefinition(
        skill_id="read_logistics",
        semantic_version="v2",
        domain="fulfillment",
        description="读取当前登录用户订单的物流异常摘要",
        input_schema_ref="schemas/skills/read_logistics.input.json",
        output_schema_ref="schemas/skills/read_logistics.output.json",
        action_mode="read",
        estimated_latency_ms=300,
        estimated_model_cost="none",
        artifact_kinds=["logistics_fact"],
        examples=["订单已发货但三天没有物流更新"],
        discovery_terms=["物流", "发货", "配送", "延误"],
    ),
    SkillDefinition(
        skill_id="read_inventory",
        semantic_version="v1",
        domain="inventory",
        description="读取服务端提供的 SKU 可用库存与替换摘要",
        input_schema_ref="schemas/skills/read_inventory.input.json",
        output_schema_ref="schemas/skills/read_inventory.output.json",
        action_mode="read",
        estimated_latency_ms=250,
        estimated_model_cost="none",
        artifact_kinds=["inventory_fact"],
        examples=["检查替代 SKU 是否有现货"],
        discovery_terms=["库存", "现货", "补发", "替代"],
    ),
    SkillDefinition(
        skill_id="retrieve_policy",
        semantic_version="v2",
        domain="knowledge",
        description="检索版本化售后政策证据，不处理实时订单事实",
        input_schema_ref="schemas/skills/retrieve_policy.input.json",
        output_schema_ref="schemas/skills/retrieve_policy.output.json",
        action_mode="read",
        estimated_latency_ms=600,
        estimated_model_cost="embedding_only",
        artifact_kinds=["policy_evidence"],
        examples=["查询质量问题退货的运费规则"],
        discovery_terms=["政策", "规则", "运费", "退货"],
    ),
    SkillDefinition(
        skill_id="list_service_applications",
        semantic_version="v1",
        domain="after_sales",
        description="列出当前用户可见的售后申请摘要",
        input_schema_ref="schemas/skills/list_service_applications.input.json",
        output_schema_ref="schemas/skills/list_service_applications.output.json",
        action_mode="read",
        estimated_latency_ms=350,
        estimated_model_cost="none",
        artifact_kinds=["after_sales_fact"],
        examples=["查看我已有的售后申请"],
        discovery_terms=["售后", "申请", "进度", "退款"],
    ),
    SkillDefinition(
        skill_id="build_service_resolution",
        semantic_version="v1",
        domain="after_sales",
        description="根据已验证事实生成结构化候选解决方案",
        input_schema_ref="schemas/skills/build_service_resolution.input.json",
        output_schema_ref="schemas/skills/build_service_resolution.output.json",
        # This only composes safe candidate summaries from existing fact
        # references.  It has no business side effect and may therefore be a
        # normal read step rather than a hidden draft write.
        action_mode="read",
        estimated_latency_ms=100,
        estimated_model_cost="none",
        artifact_kinds=["resolution_candidate"],
        examples=["比较换货、退款和人工协同方案"],
        discovery_terms=["方案", "换货", "退款", "售后"],
        requires_confirmation=False,
    ),
    SkillDefinition(
        skill_id="create_after_sales_draft",
        semantic_version="v1",
        domain="after_sales",
        description="创建可见但尚未提交的售后草案",
        input_schema_ref="schemas/skills/create_after_sales_draft.input.json",
        output_schema_ref="schemas/skills/create_after_sales_draft.output.json",
        action_mode="draft",
        estimated_latency_ms=400,
        estimated_model_cost="none",
        artifact_kinds=["action_result"],
        examples=["准备一个退货退款草案"],
        discovery_terms=["草案", "退货", "退款", "售后"],
        requires_confirmation=True,
    ),
    SkillDefinition(
        skill_id="amend_after_sales_draft",
        semantic_version="v1",
        domain="after_sales",
        description="修改尚未提交的售后草案",
        input_schema_ref="schemas/skills/amend_after_sales_draft.input.json",
        output_schema_ref="schemas/skills/amend_after_sales_draft.output.json",
        action_mode="draft",
        estimated_latency_ms=400,
        estimated_model_cost="none",
        artifact_kinds=["action_result"],
        examples=["补充售后草案说明"],
        discovery_terms=["修改", "补充", "草案", "售后"],
        requires_confirmation=True,
    ),
    SkillDefinition(
        skill_id="commit_after_sales_action",
        semantic_version="v1",
        domain="after_sales",
        description="提交经客户确认的售后动作，由 Java 校验并写入",
        input_schema_ref="schemas/skills/commit_after_sales_action.input.json",
        output_schema_ref="schemas/skills/commit_after_sales_action.output.json",
        action_mode="commit",
        estimated_latency_ms=700,
        estimated_model_cost="none",
        artifact_kinds=["action_result", "async_task"],
        examples=["客户确认后提交售后申请"],
        discovery_terms=["提交", "确认", "申请", "售后"],
        requires_confirmation=True,
    ),
    SkillDefinition(
        skill_id="open_human_case",
        semantic_version="v1",
        domain="collaboration",
        description="为当前任务创建带摘要引用的人工协同案件",
        input_schema_ref="schemas/skills/open_human_case.input.json",
        output_schema_ref="schemas/skills/open_human_case.output.json",
        action_mode="async_task",
        estimated_latency_ms=500,
        estimated_model_cost="none",
        artifact_kinds=["async_task"],
        examples=["事实不足且需要人工核验"],
        discovery_terms=["人工", "协同", "投诉", "核验"],
        requires_confirmation=True,
    ),
    SkillDefinition(
        skill_id="request_customer_evidence",
        semantic_version="v1",
        domain="collaboration",
        description="创建受限补件/澄清任务并等待客户输入",
        input_schema_ref="schemas/skills/request_customer_evidence.input.json",
        output_schema_ref="schemas/skills/request_customer_evidence.output.json",
        action_mode="async_task",
        estimated_latency_ms=350,
        estimated_model_cost="none",
        artifact_kinds=["async_task"],
        examples=["请求客户补充问题描述"],
        discovery_terms=["补件", "补充", "材料", "澄清"],
        requires_confirmation=True,
    ),
    SkillDefinition(
        skill_id="schedule_follow_up",
        semantic_version="v1",
        domain="collaboration",
        description="创建后续跟进任务；未配置真实消息系统时返回待人工状态",
        input_schema_ref="schemas/skills/schedule_follow_up.input.json",
        output_schema_ref="schemas/skills/schedule_follow_up.output.json",
        action_mode="async_task",
        estimated_latency_ms=350,
        estimated_model_cost="none",
        artifact_kinds=["async_task"],
        examples=["安排下次跟进提醒"],
        discovery_terms=["跟进", "提醒", "后续"],
        requires_confirmation=True,
    ),
    SkillDefinition(
        skill_id="search_task_memory",
        semantic_version="v1",
        domain="runtime",
        description="查询当前用户/任务范围内的脱敏历史摘要",
        input_schema_ref="schemas/skills/search_task_memory.input.json",
        output_schema_ref="schemas/skills/search_task_memory.output.json",
        action_mode="read",
        estimated_latency_ms=50,
        estimated_model_cost="none",
        artifact_kinds=["memory_hint"],
        examples=["查找上次已确认的处理偏好"],
        discovery_terms=["上次", "历史", "偏好", "记忆"],
    ),
    SkillDefinition(
        skill_id="spawn_subtask",
        semantic_version="v1",
        domain="runtime",
        description="为调查、方案比较或人工协同创建一个受控子任务",
        input_schema_ref="schemas/skills/spawn_subtask.input.json",
        output_schema_ref="schemas/skills/spawn_subtask.output.json",
        action_mode="async_task",
        estimated_latency_ms=50,
        estimated_model_cost="none",
        artifact_kinds=["async_task"],
        examples=["将库存调查拆为独立子任务"],
        discovery_terms=["子任务", "并行", "调查", "比较"],
    ),
)


def list_skills(*, role: str = "customer") -> list[SkillDefinition]:
    return [skill for skill in _CATALOG if role in skill.allowed_roles]


def get_skill(skill_id: str, *, role: str = "customer") -> SkillDefinition | None:
    return next((skill for skill in list_skills(role=role) if skill.skill_id == skill_id), None)


def discover_skills(query: str, *, role: str = "customer", limit: int = 8) -> list[SkillDefinition]:
    """Deterministic lexical discovery over metadata, not a business router."""

    normalized = " ".join((query or "").lower().split())
    tokens = set(normalized.replace("，", " ").replace("。", " ").split())
    # Chinese goals usually have no whitespace.  Add short CJK phrases strictly
    # for matching the versioned catalog descriptions/examples; this exposes a
    # bounded capability set, it does not classify a business intent or select
    # a business outcome.
    for phrase in re.findall(r"[\u4e00-\u9fff]{2,}", normalized):
        tokens.add(phrase)
        tokens.update(phrase[index : index + 2] for index in range(len(phrase) - 1))
    scored: list[tuple[int, SkillDefinition]] = []
    for skill in list_skills(role=role):
        haystack = " ".join([skill.skill_id, skill.domain, skill.description, *skill.examples]).lower()
        score = sum(1 for token in tokens if token and token in haystack)
        # Explicit discovery terms are catalog metadata reviewed with the Skill,
        # not a route table.  They make CJK discovery resilient without allowing
        # the server to choose a business action for the model.
        score += sum(4 for term in skill.discovery_terms if term.lower() in normalized)
        if skill.domain in normalized:
            score += 1
        scored.append((score, skill))
    scored.sort(key=lambda pair: (-pair[0], pair[1].skill_id))
    # Discovery always exposes a bounded set; a zero lexical score still
    # returns core runtime capabilities so the Executor can ask for a better
    # plan without receiving the entire catalog.
    selected = [skill for score, skill in scored if score > 0][:limit]
    if not selected:
        selected = [
            skill
            for skill in list_skills(role=role)
            if skill.skill_id in {"search_catalog", "read_order", "retrieve_policy", "list_service_applications"}
        ][:limit]
    return selected
