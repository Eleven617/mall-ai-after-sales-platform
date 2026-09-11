# 学习输入地图（第一轮新顺序）

> 当前证据基线：运行时代码 `52d5482455e2389cfd6c2ef15d233712607ffa9f`；live main `72/72`、holdout `36/36`、grounding `15/15`。历史 `24/72` 和 `11/15` 只作为失败归因材料，已在最终失败矩阵中标 stale，不再是当前结果。

项目现在可以冻结并进入学习；建议按以下顺序，每个模块都沿着“完整链路 → 3 个重点代码文件 → 已验证结果/边界/面试表达”学习。

## 1. Agent 运行循环

- 链路：用户消息 → TurnPlan → active/paused 任务 → Agent 只读计划 → Skill 执行 → Context/Artifact → Proposal/回答。
- 重点：`task_orchestration_service.py`、`task_runtime.py`、`task_planner.py`。
- 必会：Agent 与 Workflow 的分工、最大步数、无证据停止、任务切换和恢复。

## 2. Prompt 工程

- 链路：有限 Intent/TaskPlan Schema → 版本化提示 → 结构化输出网关 → 非法输出安全停止。
- 重点：`intent_service.py`、`structured_output_gateway.py`、`schemas/intent.py`。
- 必会：不用关键词猜意图，不把 Prompt 当权限层，失败样本如何进入 Eval。

## 3. Context Engineering

- 链路：事实投影 → Context Pack → 压缩/摘要 → Redis/任务存储 → 重启恢复 → 重新核验事实。
- 重点：`context_curator.py`、`task_memory.py`、`task_store.py`。
- 必会：active/paused/transaction_gate、脱敏、TTL、版本和不保存原始 Prompt。

## 4. RAG Engineering

- 链路：政策源 → 结构化 Chunk/Metadata → Embedding/索引 → Metadata 过滤 → Dense 检索 → Evidence Verifier。
- 重点：`chunking_service.py`、`policy_retrieval.py`、`rag_evidence_verifier.py`。
- 必会：Dense 默认证据、52 集指标、无证据拒答、RAG 不代替 Java 订单事实。

## 5. Tool/Skill 设计

- 链路：Skill Catalog → Tool Registry → Agent 提议 → 服务端白名单/参数/身份/预算 → 只读事实包。
- 重点：`skill_catalog.py`、`tool_registry.py`、`skills/commerce_gateway.py`。
- 必会：MCP 只读边界、不能自创工具、跨账号拒绝和工具结果不可改写事实。

## 6. LLMOps/Evals

- 链路：合成 EvalCase → deterministic comparator → contract_mock CI → live_model_synthetic 手动运行 → 失败归因/人工审批。
- 重点：`run_quality_agent_evaluation.py`、`evaluate_task_orchestration.py`、`release-manifest.json`。
- 必会：478/478 是合同通过，不是任务完成率；当前 live main/holdout 是合成只读网关的 72/72、36/36，Grounding 是 15/15；这些都不能扩大为真实用户泛化率。

## 7. 可靠执行

- 链路：ActionProposal → 用户确认 → Java 重读事实 → Transaction/Outbox → RabbitMQ/Worker → 幂等恢复/人工兜底。
- 重点：`AiAfterSalesApplicationServiceImpl.java`、`AiAfterSalesOutboxPublisher.java`、`AiAfterSalesStatusEventReceiver.java`。
- 必会：JWT/owner/资格/状态/幂等、重试、超时、故障注入、不能伪造外部履约成功。

## 学习时的面试练习

每个模块都要能回答：一次请求从哪里进来？谁决定下一步？哪些字段是模型输出？谁验证？哪里可以暂停/恢复？如果模型/Redis/Java/RabbitMQ失败，系统如何停止且不写错？
