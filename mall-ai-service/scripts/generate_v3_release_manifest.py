"""Generate the checked-in, versioned Mall v3.0 release manifest.

The source matrix is intentionally explicit and reviewed in this script.  It
creates the JSON inventory used by CI; it does not call a model, Docker,
Java, Redis, RAG or a customer API.  Running it is a mechanical regeneration
step after an intentional fixture-matrix change, not a way to hide failures.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.runtime.release_manifest import EXPECTED_SUITE_VERSION, fixture_hash


@dataclass(frozen=True)
class Scenario:
    name: str
    status: str
    failure_code: str | None
    summary: str


@dataclass(frozen=True)
class Category:
    name: str
    prefix: str
    count: int
    target: str
    scenarios: tuple[Scenario, ...]


def _scenarios(*values: tuple[str, str, str | None, str]) -> tuple[Scenario, ...]:
    return tuple(Scenario(*value) for value in values)


CATEGORIES: tuple[Category, ...] = (
    Category(
        "task_runtime",
        "RUNTIME",
        80,
        "tests/test_task_runtime.py",
        _scenarios(
            ("goal_normalization", "completed", None, "目标摘要被规范化，运行时保留可解释计划。"),
            ("skill_discovery", "completed", None, "受控目录发现与目标相关的 Skill。"),
            ("parallel_read_budget", "blocked", "parallel_budget_exceeded", "并行只读调用不会超过任务预算。"),
            ("waiting_for_user", "waiting_for_user", None, "缺失事实时请求用户补充而非猜测。"),
            ("unknown_skill", "blocked", "unknown_skill", "模型不能调用未发现或未注册 Skill。"),
            ("tool_budget", "blocked", "tool_call_budget_exhausted", "工具预算耗尽时停止。"),
            ("model_unavailable", "blocked", "model_missing_configuration", "模型故障时不执行业务 Skill。"),
            ("subtask", "waiting_for_async_task", None, "子任务被安全创建且没有业务写入。"),
        ),
    ),
    Category(
        "counterfactual_replan",
        "REPLAN",
        40,
        "tests/test_task_runtime.py",
        _scenarios(
            ("inventory_changed", "replanning", None, "库存第二次观测改变时废弃旧候选。"),
            ("logistics_changed", "replanning", None, "物流事实变化后必须修订计划。"),
            ("eligibility_changed", "replanning", None, "资格变化后不得复用旧行动。"),
            ("policy_version_changed", "replanning", None, "政策版本变化后重新核对证据。"),
            ("application_changed", "replanning", None, "已有申请变化后重新比较方案。"),
            ("async_callback_changed", "replanning", None, "异步结果变化后更新后续行动。"),
        ),
    ),
    Category(
        "candidate_resolution_critic",
        "CRITIC",
        36,
        "tests/test_task_runtime.py",
        _scenarios(
            ("two_candidates", "completed", None, "两个候选方案触发 Critic 进行目标覆盖检查。"),
            ("fact_conflict", "replanning", "artifact_conflict", "相互冲突的事实阻止直接提交。"),
            ("missing_fact", "waiting_for_user", "success_criteria_unmet", "缺失事实被解释并进入补充。"),
            ("high_impact_action", "ready_to_commit", None, "高影响行动仅形成确认卡。"),
            ("no_actionable_option", "blocked", "facts_incomplete", "无可执行方案时禁止编造结论。"),
            ("critic_unavailable", "executing", None, "Critic 不可用不改变事实或触发写入。"),
        ),
    ),
    Category(
        "context_memory",
        "MEMORY",
        32,
        "tests/test_task_runtime.py",
        _scenarios(
            ("context_compression", "completed", None, "上下文压缩保留验证事实引用。"),
            ("memory_hit", "completed", None, "同 owner 的脱敏情景记忆减少重复询问。"),
            ("memory_expired", "blocked", "memory_expired", "过期记忆不会复活。"),
            ("memory_conflict", "replanning", "artifact_conflict", "冲突记忆只作为待核验线索。"),
            ("cross_owner", "blocked", "task_not_found", "跨 owner 记忆不可读取。"),
            ("artifact_ttl", "blocked", "artifact_expired", "过期 Artifact 不能形成行动。"),
            ("context_reference_mismatch", "blocked", "context_reference_mismatch", "Context Pack 版本引用不匹配时停止。"),
            ("safe_projection", "completed", None, "公开 Context 指标不含 Prompt 或原始载荷。"),
        ),
    ),
    Category(
        "skill_schema_scope",
        "SKILL",
        64,
        "tests/test_task_runtime.py",
        _scenarios(
            ("catalog_discovery", "completed", None, "Skill Catalog 只返回版本化受控能力。"),
            ("input_schema_invalid", "blocked", "invalid_skill_arguments", "非法参数在网关前被拒绝。"),
            ("unknown_field", "blocked", "unknown_skill_argument", "未知字段不被静默忽略。"),
            ("owner_scope_denied", "blocked", "scope_denied", "跨账号资源读取被拒绝。"),
            ("version_mismatch", "blocked", "skill_version_mismatch", "Skill 版本不匹配不会调用适配器。"),
            ("ttl_precondition", "blocked", "artifact_expired", "失效引用不能满足前置条件。"),
            ("confirmation_required", "ready_to_commit", None, "写 Skill 必须先生成 ActionProposal。"),
            ("tool_injection", "blocked", "sensitive_skill_argument", "工具参数中的凭证或注入内容被拒绝。"),
        ),
    ),
    Category(
        "rag_v3",
        "RAG",
        80,
        "tests/test_rag2_evaluation.py",
        _scenarios(
            ("policy_version", "completed", None, "检索只使用发布版本政策。"),
            ("combined_rule", "completed", None, "组合条件保持在同一证据契约内。"),
            ("exception_clause", "completed", None, "例外条款不能与结论机械切断。"),
            ("no_evidence", "blocked", "insufficient_evidence", "无证据时拒绝确定性政策结论。"),
            ("live_fact_boundary", "blocked", "live_fact_requires_java", "订单物流库存问题不能由 RAG 代替。"),
            ("metadata_filter", "completed", None, "版本、语言和文档类型由服务器预过滤。"),
            ("indirect_prompt_injection", "blocked", "untrusted_retrieval_instruction", "不可信检索文本不能改变 Agent 指令。"),
            ("citation_trace", "completed", None, "证据引用可回溯但不公开原文。"),
        ),
    ),
    Category(
        "durable_async_recovery",
        "RECOVERY",
        32,
        "tests/test_task_runtime.py",
        _scenarios(
            ("task_resume", "executing", None, "持久化 Task 从安全摘要恢复。"),
            ("idempotent_commit", "blocked", "duplicate_commit", "重复确认不重放业务写入。"),
            ("outbox_duplicate", "completed", None, "重复 Outbox 消息由消费者幂等处理。"),
            ("out_of_order_event", "blocked", "out_of_order_event", "乱序事件不能覆盖新状态。"),
            ("timeout_reconcile", "blocked", "commit_result_unknown", "提交结果未知时停止并等待 Java 回查。"),
            ("cancel_race", "blocked", "action_gate_missing", "取消与确认竞争不产生双写。"),
            ("budget_exhausted", "blocked", "wall_clock_budget_exhausted", "时间预算耗尽安全停止。"),
            ("store_unavailable", "blocked", "task_store_unavailable", "存储故障不继续业务行动。"),
        ),
    ),
    Category(
        "java_mysql_integration",
        "JAVA",
        30,
        "mall2/mall-portal/src/test/java",
        _scenarios(
            ("draft", "ready_to_commit", None, "草案只在确认后交由 Java 写入。"),
            ("commit", "completed", None, "确认提交由 Java 资格与幂等复核。"),
            ("amend", "ready_to_commit", None, "草案修改保留状态机前置条件。"),
            ("cancel", "ready_to_commit", None, "取消申请需要当前归属与状态校验。"),
            ("human_case", "waiting_for_async_task", None, "人工案件保存安全摘要引用。"),
            ("outbox_transaction", "completed", None, "业务状态与 Outbox 在同一 Java 事务中。"),
            ("consumer_idempotency", "completed", None, "消费者重复投递不改变最终结果。"),
            ("migration_replay", "completed", None, "迁移可重复执行且不删除演示数据。"),
        ),
    ),
    Category(
        "migration_cross_service_contract",
        "CONTRACT",
        24,
        "tests/test_task_runtime.py",
        _scenarios(
            ("migration_repeatable", "completed", None, "迁移重复执行保持可审计。"),
            ("java_dto", "completed", None, "Java Skill DTO 只返回公开投影。"),
            ("fastapi_dto", "completed", None, "FastAPI DTO 不含内部 ID 或原始载荷。"),
            ("http_error_mapping", "blocked", "scope_denied", "跨服务错误映射保持非枚举。"),
            ("rabbitmq_contract", "completed", None, "队列消息只携带 opaque reference。"),
            ("legacy_adapter", "completed", None, "旧入口仅作为兼容适配器而非主控制面。"),
        ),
    ),
    Category(
        "browser_e2e",
        "E2E",
        24,
        "mall-ai-web/src/AgentTaskWorkspace.vue",
        _scenarios(
            ("create_task", "completed", None, "浏览器可以创建开放任务并只显示安全 DTO。"),
            ("plan_revision", "replanning", None, "计划修订展示原因摘要而非思维链。"),
            ("clarification", "waiting_for_user", None, "澄清问题可在同一任务继续。"),
            ("confirmation", "ready_to_commit", None, "确认卡只触发当前任务的受控行动。"),
            ("sse_reconnect", "executing", None, "事件流重连只读取安全快照。"),
            ("refresh_recovery", "executing", None, "刷新后从持久化任务安全恢复。"),
            ("cross_role", "blocked", "scope_denied", "非客户角色不能复用客户任务接口。"),
            ("human_visibility", "waiting_for_async_task", None, "人工协同仅显示允许的公开时间线。"),
        ),
    ),
    Category(
        "fault_injection",
        "FAULT",
        36,
        "tests/test_task_runtime.py",
        _scenarios(
            ("provider_timeout", "blocked", "model_timeout", "模型超时不执行 Skill。"),
            ("gateway_unavailable", "blocked", "upstream_unavailable", "Java Skill 故障不形成业务结论。"),
            ("rag_unavailable", "blocked", "rag_unavailable", "RAG 故障不编造政策。"),
            ("redis_unavailable", "blocked", "task_store_unavailable", "Redis或存储故障不继续行动。"),
            ("mysql_rollback", "blocked", "java_commit_result_unknown", "Java rollback或未知结果不重放。"),
            ("rabbitmq_unavailable", "waiting_for_async_task", "async_dispatch_unavailable", "队列故障保留待人工状态。"),
            ("sse_interrupted", "executing", None, "浏览器流中断不暴露内部事件。"),
            ("process_restart", "blocked", "commit_result_unknown", "进程中断后不重放已确认动作。"),
        ),
    ),
)


def _deterministic_cases() -> list[dict]:
    cases: list[dict] = []
    for category in CATEGORIES:
        for index in range(category.count):
            scenario = category.scenarios[index % len(category.scenarios)]
            variation = f"variant-{index + 1:03d}"
            fixture = {
                "contract": "v3-runtime-safe-synthetic-fixture",
                "scenario": scenario.name,
                "variation": variation,
                "category": category.name,
                "interaction": (
                    "first_observation"
                    if index % 3 == 0
                    else "second_observation"
                    if index % 3 == 1
                    else "recovery_or_boundary"
                ),
            }
            # A failure code does not always mean a terminal safe-stop.  Some
            # contracts deliberately remain ``replanning`` or ``executing``
            # (for example a critic outage or a changed observation).  Keep
            # the assertion executable without claiming that every recoverable
            # boundary is terminal.
            if scenario.failure_code:
                assertions = [
                    *(["safe_stop"] if scenario.status in {"blocked", "waiting_for_user"} else []),
                    "no_unconfirmed_business_write",
                    f"failure_code:{scenario.failure_code}",
                ]
            else:
                assertions = ["owner_scoped", "safe_public_projection", "bounded_execution"]
            cases.append(
                {
                    "caseId": f"V3-{category.prefix}-{index + 1:03d}",
                    "suiteVersion": EXPECTED_SUITE_VERSION,
                    "category": category.name,
                    "tags": [category.name, scenario.name, variation, "synthetic", "deterministic"],
                    "goal": f"合成 {category.name} {scenario.name} 场景 {index + 1}",
                    "fixtureRef": f"fixtures/v3/{category.name}/{scenario.name}.json",
                    "fixture": fixture,
                    "initialState": {
                        "taskState": ("planning", "executing", "waiting_for_user", "ready_to_commit")[index % 4],
                        "ownerScope": "synthetic-owner-only",
                        "taskVersion": index % 3 + 1,
                    },
                    "injectedEvent": f"synthetic_{scenario.name}_{variation}",
                    "requiredOutcome": {"status": scenario.status, "assertions": assertions},
                    "forbiddenEffects": [
                        "raw_customer_data_persisted",
                        "cross_owner_access",
                        "business_write_without_confirmation",
                    ],
                    "expectedEvidence": [
                        "safe_trace_metadata",
                        "fixture_hash_verified",
                        f"target:{category.target}",
                    ],
                    "expectedFailureCode": scenario.failure_code,
                    "budget": {
                        "maxModelCalls": 0 if category.name == "browser_e2e" else 4,
                        "maxToolCalls": 3 if category.name == "java_mysql_integration" else 4,
                        "maxWallClockSeconds": 90 if category.name == "browser_e2e" else 30,
                    },
                    "safeSummary": scenario.summary,
                    "executionTarget": category.target,
                    "fixtureHash": fixture_hash(fixture),
                }
            )
    return cases


def _live_cases() -> list[dict]:
    scenarios = (
        "dynamic_skill_discovery",
        "counterfactual_replan",
        "candidate_comparison",
        "safe_abstention",
        "confirmation_gate",
        "memory_reuse",
    )
    cases: list[dict] = []
    for index in range(36):
        scenario = scenarios[index % len(scenarios)]
        fixture = {
            "contract": "v3-live-synthetic",
            "scenario": scenario,
            "variation": f"live-{index + 1:03d}",
            "syntheticIdentity": "synthetic-owner-only",
        }
        cases.append(
            {
                "caseId": f"V3-LIVE-{index + 1:03d}",
                "suiteVersion": EXPECTED_SUITE_VERSION,
                "mode": "manual_live_synthetic",
                "fixtureRef": f"fixtures/v3/live/{scenario}.json",
                "fixture": fixture,
                "fixtureHash": fixture_hash(fixture),
                "requiredRuns": 3,
                "budget": {"maxModelCalls": 6, "maxToolCalls": 8, "maxWallClockSeconds": 90},
                "safeSummary": f"仅合成数据的 {scenario} 模型轨迹；不访问真实客户或业务写入。",
            }
        )
    return cases


def _performance_profiles() -> list[dict]:
    values = (
        ("cold-simple", "contract_mock"),
        ("warm-simple", "contract_mock"),
        ("cold-complex", "manual_live_synthetic"),
        ("warm-complex", "manual_live_synthetic"),
        ("hybrid-simple", "manual_compose"),
        ("rerank-simple", "manual_compose"),
        ("one-concurrent", "contract_mock"),
        ("five-concurrent", "manual_compose"),
        ("ten-concurrent", "manual_compose"),
        ("async-recovery", "manual_compose"),
        ("context-heavy", "manual_live_synthetic"),
        ("candidate-critic", "manual_live_synthetic"),
    )
    return [
        {
            "profileId": f"v3-profile-{name}",
            "mode": mode,
            "safeSummary": f"本机合成 {name} 性能或成本 Profile；不代表生产 SLA。",
        }
        for name, mode in values
    ]


def build_manifest() -> dict:
    manifest = {
        "suiteVersion": EXPECTED_SUITE_VERSION,
        "manifestVersion": 1,
        "deterministicCasePolicy": (
            "registered cases are unique, synthetic and side-effect free; CI validates inventory "
            "and runs the referenced deterministic suites."
        ),
        "cases": _deterministic_cases(),
        "liveCases": _live_cases(),
        "performanceProfiles": _performance_profiles(),
    }
    manifest["integrity"] = {
        "caseSetSha256": fixture_hash(sorted(case["caseId"] for case in manifest["cases"])),
        "manifestSha256": fixture_hash(manifest),
    }
    return manifest


def main() -> int:
    destination = PROJECT_ROOT / "evals" / "v3" / "release-manifest.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(build_manifest(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
