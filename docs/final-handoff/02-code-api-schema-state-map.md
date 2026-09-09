# 代码、API、Schema 与状态映射

## FastAPI 入口与公开路由

| 层 | 文件 | 责任 |
| --- | --- | --- |
| 应用入口 | `mall-ai-service/app/main.py` | FastAPI 应用、依赖与路由注册 |
| 客服 | `app/routers/customer_service.py` | 统一售后、政策与会话公开 DTO |
| 任务工作台 | `app/routers/agent_tasks.py` | AgentTask、计划、Artifact、Proposal 投影 |
| 运营 | `app/routers/operations.py` | 受限聚合和运营只读接口 |
| 人工案件 | `app/routers/service_operations.py` | 案件队列、领取、补件、处理、结案 |
| 质量 | `app/routers/quality.py` | 合成评测和质量摘要 |
| MCP | `app/routers/mcp.py` | 只读、角色隔离的工具入口 |
| 身份/健康 | `app/routers/authentication.py`、`health.py` | 登录、健康检查和公开 readiness |

主要公开路径前缀为 `/customer-service`、`/agent-tasks`、`/operations`、`/service-operations`、`/quality`、`/mcp`、`/auth`、`/health`。

## Agent Runtime 与任务状态

- 合同：`app/schemas/task_orchestration.py`、`app/schemas/intent.py`、`app/schemas/agent_task.py`。
- 调度：`app/services/task_orchestration_service.py`、`app/runtime/task_runtime.py`、`app/services/task_planner.py`。
- 上下文：`app/runtime/task_memory.py`、`app/runtime/context_curator.py`、`app/runtime/task_store.py`、`app/services/conversation_state.py`、`conversation_store.py`。
- 评判与供应商：`app/runtime/resolution_critic.py`、`app/runtime/providers.py`、`app/services/structured_output_gateway.py`。
- 任务模型包含受限 `TaskKind`、`TaskStatus`、`TaskSnapshot`、`TurnPlan`、`active_task`、`paused_task` 和 `transaction_gate`。公开 DTO 只给脱敏摘要和 opaque reference，不给 task/checkpoint 原始载荷。

## 售后执行边界

- P0/语义：`app/services/intent_service.py`、`app/services/customer_service.py`。
- 统一图：`app/services/unified_after_sales_graph.py`。
- 草稿/Proposal：`app/services/after_sales_application_service.py`、`after_sales_application_state.py`。
- 受限能力：`app/services/skill_catalog.py`、`tool_registry.py`、`app/skills/catalog.py`、`app/skills/commerce_gateway.py`。
- 诊断只读调查：`app/services/diagnosis_agent.py`、`durable_diagnosis.py`，工具名/参数/次数/超时仍由服务端校验。

## RAG 链路

`chunking_service.py` → `policy_metadata.py` → `embedding_service.py` → `vector_store.py` → `policy_retrieval.py` / `rag_service.py` → `rag_evidence_verifier.py`。当前 Dense 是默认；BM25+Dense+RRF 和 Cross-Encoder Rerank 仅作为可复现实验。Chunk 保留标题路径和版本/类别/语言等元数据，业务订单事实不由 RAG 代替。

## Java 权威服务

- Portal Controller：`mall2/mall-portal/src/main/java/com/macro/mall/portal/controller/AiAfterSalesApplicationController.java`、`AiCaseHandoffController.java`、`AiCustomerConversationController.java`、`AiServiceCaseController.java`。
- Portal Service：`.../service/impl/AiAfterSalesApplicationServiceImpl.java`、`AiCaseHandoffServiceImpl.java`、`AiServiceCaseServiceImpl.java`。
- Outbox/履约：`AiAfterSalesOutboxPublisher.java`、`AiAfterSalesStatusEventReceiver.java`、`AiAfterSalesFulfillmentCommandReceiver.java`、`DemoAiAfterSalesFulfillmentAdapter.java`、`ManualAiAfterSalesFulfillmentAdapter.java`。
- DAO：`AiAfterSalesApplicationDao`、`AiAfterSalesActionDao`、`AiAfterSalesOutboxDao` 等。
- Admin 运营实现位于 `mall2/mall-admin/.../operations/...` 和 `.../serviceoperations/...`。

Java 负责 JWT、owner scope、资格、状态机、幂等键、事务和最终写入；Outbox 消息只携带 opaque reference，消费者需幂等。

## 前端

`mall-ai-web/src/App.vue`、`AgentTaskWorkspace.vue`、`OperationsPage.vue`、`ServiceOperationsPage.vue`、`QualityPage.vue`、`api.ts`、`types.ts`。前端只呈现安全 DTO、候选和确认卡，不保存 Token、内部 ID、RAG chunk、原始工具载荷或 Trace。

