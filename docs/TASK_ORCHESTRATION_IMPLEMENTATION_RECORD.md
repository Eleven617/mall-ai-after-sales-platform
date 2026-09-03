# 统一售后 Agent：任务感知编排实施记录

更新时间：2026-09-02。本记录对应 [一次性升级方案](AGENT_TASK_ORCHESTRATION_ONE_SHOT_UPGRADE.md)，只陈述本机代码和验收事实；不包含账号、密码、Token、订单号、原始聊天、RAG 原文、完整工具载荷或 Docker 卷数据。

## 完成状态

本次一次性切换已完成。客户入口不再由旧的 `pending_*` 优先级解释下一条消息：每条新消息先调用受限、结构化的任务感知 P0，生成闭集 `TurnPlan`，再由运行时做状态迁移和受控分派。

```text
客户消息
  -> Task-aware P0：业务意图 + 任务关系 + 路由 + 确认意图
  -> TaskOrchestrationService：active / paused / transaction gate
  -> 只读 Agent 或 RAG 或统一售后 Workflow
  -> Java：事实、权限、资格、状态机、幂等、事务、最终写入
```

## 用户可见性、验收路径与非目标

- 客户可见：轻量“当前处理任务”或“已暂存任务”卡片，包含固定任务标签和安全提示；可自然语言继续、切题或放弃，不需要输入 `interrupt`、任务 ID 或 checkpoint ID。
- 客户不可见：`TurnPlan`、内部任务 ID、所有权指纹、Redis 载荷、原始工具结果、RAG chunk/分数、Trace、Token、Java 内部标识。
- 实际验收路径：网页代理 → FastAPI → 本地 DeepSeek 可用路径 / 本地 RAG → Redis；本次验证“缺标识诊断 → 政策临时切题 → 服务重启 → 同会话自然恢复”，并检查公开 DTO 字段。
- 非目标：不增加第四个 Agent、不引入无限并行任务、长期记忆、自动业务写入或通用 Skill Loader；不把已提交 Java 业务动作伪装为可由 AI 回滚。
- 成本与延迟：任务状态迁移和安全摘要不增加模型调用。每条新消息仍先有一次 P0；政策临时切题沿用既有 RAG/证据核验调用。现场两条合成请求约 2.3 s 与 5.9 s，属于本机一次测量，不是 SLA 或成本结论。
- 失败回退：P0/结构化 JSON 不可用时本轮安全停止，不调用 RAG、只读工具、统一售后图或 Java 写接口；过期、归属不匹配或无法安全迁移的旧短期 Redis 状态按过期处理。

## 实际实现

| 范围 | 关键位置 | 实际变化 |
| --- | --- | --- |
| 结构化合同 | `mall-ai-service/app/schemas/task_orchestration.py`、`schemas/intent.py`、`schemas/conversation.py` | 新增 `TaskSnapshot`、`TurnPlan`、`TransactionGate` 与安全投影；合同拒绝额外字段、敏感任务摘要和未闭合枚举。 |
| 会话状态 | `services/conversation_state.py` | Redis 会话保存最多一个 active、一个 paused 任务以及独立交易关口；给 P0 的上下文仅含脱敏摘要，旧 pending 缓存不能被猜测迁移。 |
| 入口与 P0 | `services/customer_service.py`、`services/intent_service.py`、`services/task_orchestration_service.py` | P0 在任何 pending/恢复前执行；支持继续、临时切题、恢复、放弃、冲突澄清和自然确认；确认只作用于服务端当前有效交易关口。 |
| 售后/诊断桥接 | `services/unified_after_sales_graph.py`、`services/after_sales_application_service.py`、`services/after_sales_application_state.py` | 缺标识改为普通 waiting-input 任务；草案可暂存；Proposal/Action 不阻塞政策或聊天，且第二张确认卡不能覆盖第一张。 |
| 客户页面 | `mall-ai-web/src/App.vue`、`mall-ai-web/src/types.ts`、公开 DTO schema | 仅展示 `task_status`、固定标签和固定提示，不接收或保存内部任务/检查点标识。 |
| 可观测性 | `services/trace_service.py` | Trace 只记录允许的任务关系、任务类别、确认意图和版本化枚举，不记录模型推理链或客户敏感内容。 |

## 自动化与本机验证

| 范围 | 命令 / 路径 | 实际结果 |
| --- | --- | --- |
| FastAPI 全量回归 | `mall-ai-service/.venv/Scripts/python.exe -m pytest -q` | **317 passed，7 subtests passed**；1 条第三方弃用警告。新增/更新任务切换、暂停恢复、交易关口保护、模型失败安全停止、公开 DTO 与本地代理绕过回归。 |
| Vue 生产构建 | `mall-ai-web: npm run build` | `vue-tsc --noEmit` 与 Vite production build 成功。 |
| Java portal 定向 | Maven 显式 `-DskipTests=false` 的售后/Outbox/人工案件集合 | **22/22 passed**。 |
| Java admin 定向 | Maven 显式 `-DskipTests=false` 的运营/开发者/人工处理角色集合 | **14/14 passed**。 |
| Compose 合同 | `docker compose config --quiet` | 成功。 |
| Docker / 网页代理 | `docker compose up -d --build mall-ai-service mall-ai-web`；经 `http://127.0.0.1:5173/api/customer-service` | 重建成功，八个常驻服务健康；两次合成客户路径和一次重启恢复均为 HTTP 200。 |
| 任务编排评测 | `scripts/evaluate_task_orchestration.py` | `contract_mock` **11/11**；手动 `live_model_synthetic` **10/10**，总 **23.1 s**、p95 **4.0 s**。两档均只使用版本化合成数据。 |

## 现场结果与边界

已在最新容器中实际确认：缺订单标识时公开任务状态为 `active`；同会话政策提问后状态为 `paused`；仅重启 `mall-ai-service` 且 Redis 保留后，后续自然语言恢复为 `active`。代理公开响应没有 `intent`、`rag_sources`、`rag_context`、`tool_result`、`trace`、任务 ID 或 checkpoint ID。

尚未把下列项目宣称为完成：真实生产部署/SLA、全部自然语言表达的任务关系准确率、完整登录态下的每一种 Proposal/Action 现场组合、真实支付/仓储/物流/维修集成、远程 GitHub Actions 本轮绿灯。交易关口的“不抢占、自然确认、自然撤回、不可覆盖”由本次 FastAPI 合同测试覆盖；此前独立的登录态统一售后网站代理验收仍在 [测试与演示证据](TEST_AND_DEMO_EVIDENCE.md) 中保留。

## 回退依据

本轮前代码快照位于 `snapshots/task-orchestration-one-shot-20260902-1815`。回退应使用版本控制和数据库备份；不恢复旧 pending 优先运行时逻辑，不删除现有命名卷、演示数据或已提交的 Java 业务记录。
