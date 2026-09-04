# Mall 最终升级实施记录

更新时间：2026-09-02（本地工作区、保留原有命名卷）。

## 结论与口径

本次以 `C:\Users\12969\Desktop\hermes\output\Mall_可信AI售后与AgentOps平台_最终需求对接文档.md` 为唯一功能契约，对 FR-01～FR-19 的代码、自动化回归、Compose 与可执行本地现场路径进行了收口。它是本地合成 Demo 和 Apache-2.0 上游 mall 的二次开发，**不是**生产上线、真实客户系统、自动退款服务或线上模型路由平台。

Java 始终是 JWT、订单/物流/资格、售后状态机、幂等、事务、Outbox 与最终写入权威；FastAPI 只做受限模型编排、公开 DTO、Redis 短期状态、RAG 和离线评测，绝不直连商城业务数据库。

> 2026-09-02 后续收口：客户入口已从旧的 pending 优先恢复改为任务感知 P0 优先。`active_task` 与最多一个 `paused_task` 用于普通多轮澄清和自然恢复；缺订单号不再默认进入 Durable `interrupt()`。Proposal/Action 是不抢占聊天的独立 transaction gate。详见 [任务感知编排实施记录](TASK_ORCHESTRATION_IMPLEMENTATION_RECORD.md)。

## 本轮实际补强

- 诊断只读工具规划默认使用 `temperature=0`，并在订单型诊断中先固定核验唯一明确订单号对应的 Java 订单事实；后续物流/政策步骤仍由受限图循环决定。物流门面没有载体、运单或配送状态时不再被当作已核验物流事实，而是安全进入 `facts_incomplete` 并转人工。
- MCP 会话不再把所有运营主体折叠为同一 `operator` 身份：`mcp_context_resolver.py` 从 Java 已验证主体派生不可逆运行时指纹，`mcp_server.py` 用该指纹绑定会话和限流键。
- MCP JSON-RPC 参数新增最大嵌套深度 8、最大节点数 128，身份、角色、URL、SQL、文件和写操作字段仍在工具派发前拒绝。
- Build 21 网站代理脚本改为只在显式 opt-in 时通过 Java API 自举本地 A/B 合成账号与订单；重启后等待 Redis readiness，而不是只检查 FastAPI 存活。
- 统一售后网站代理脚本也支持显式 `MALL_UNIFIED_BOOTSTRAP_LOCAL_DEMO=true` 本地自举；它只经 Java 公共演示 API 创建进程内合成 A/B 账号与订单，再验证确认、幂等目标、取消确认与跨账号拒绝。
- 新增 `mall-ai-service/scripts/verify_mcp_authenticated_live.py`：经 Vue 代理验证 initialize、tools/list、Java 事实工具、SSE 空就绪流、跨账号 session/订单拒绝、参数注入拒绝和会话关闭。脚本不输出密码、Token、订单号、MCP session 或工具载荷。
- 新增根目录 `scripts/Initialize-LocalDemoAccess.ps1`：本地维护者自己在终端输入一次密码，脚本才会在 Compose MySQL 中建立或轮换固定的最小权限演示身份，并精确清除对应 Redis 认证缓存；提交后在当前进程内通过相应 FastAPI 登录边界做无凭据回显的可用性验证。密码只在当前进程中用于 BCrypt 哈希与验证，不写文件、文档或 Git。它是本地 Demo 初始化，不是 FastAPI/浏览器可调用的运行时权限接口。

## FR 实现映射

| FR | 已实现的关键边界 | 代表实现/测试 |
| --- | --- | --- |
| FR-01 | 登录会员绑定会话、Redis 草案和 Durable checkpoint；猜测、跨账号、删除后恢复均拒绝。 | `routers/customer_service.py`、`conversation_scope.py`、`durable_diagnosis.py`、`test_conversation_*`、`test_durable_diagnosis.py` |
| FR-02 | 政策与实时事实分层；版本化 Chunk/Metadata、Dense/BM25/RRF/Rerank 实验、证据核验和无证据安全停止。 | `rag_service.py`、`policy_retrieval.py`、`chunking_service.py`、`rag_evidence_verifier.py`、RAG/Chunk 测试与评测 |
| FR-03 | 订单、物流、资格、申请状态仅走 Java 最小投影；客户只接收安全事实卡和查询时间。 | `mall_client.py`、`fact_presentation_service.py`、Java `AiAfterSalesApplicationController` |
| FR-04 | 有界只读诊断：缺标识进入普通 waiting-input 任务；任务感知 P0 负责暂停/恢复，候选歧义、工具失败和事实不足均澄清或安全停止。 | `diagnosis_agent.py`、`task_orchestration_service.py`、`test_diagnosis_*`、`test_task_orchestration_service.py` |
| FR-05 | 四类申请的统一售后图；草案绑定用户/会话/内容哈希/TTL，创建、取消、修改均先展示待确认动作。 | `unified_after_sales_graph.py`、`after_sales_application_service.py`、`test_unified_after_sales_graph.py` |
| FR-06 | FastAPI 不写业务库；Java 在提交前复核归属、商品、资格、状态、版本和幂等。 | Java `AiAfterSalesApplicationServiceImpl`、`AiAfterSalesApplicationControllerTest` |
| FR-07 | 申请/动作/审计/Outbox 同事务；发布、消费、回调和重复事件均以事件/动作幂等键保护。 | Java `AiAfterSalesOutboxPublisher`、`AiAfterSalesStatusEventReceiver`、portal 测试 |
| FR-08 | 最小 Case Handoff 只含安全事实/证据引用；运营只读 7/30 天聚合和一次结构化分析草案。 | `case_handoff_service.py`、`operations_agent.py`、`AiCaseHandoffServiceImpl` |
| FR-09 | 三个 AI 角色具备独立 Capability/Skill/入口；人工处理人员是独立 Java 角色。 | `agent_capabilities.py`、`skill_catalog.py`、角色/越权测试 |
| FR-10 | Trace、反馈候选、人工审核、合成 EvalCase 采用 allow-list 安全投影。 | `trace_service.py`、`feedback_governance_service.py`、`quality_evaluation_agent.py` |
| FR-11 | EvaluationProfile、RunManifest 和可重复 contract_mock / live_model_synthetic 边界；无线上自动路由。 | `evaluation_profile_service.py`、`quality_run_store.py`、质量页面/测试 |
| FR-12 | Streamable HTTP MCP 仅有六项只读工具；数据范围由 Java 验证身份派生，不能从参数扩权。 | `routers/mcp.py`、`mcp_server.py`、`mcp_tool_catalog.py`、合同/现场脚本 |
| FR-13 | Redis 限流、会话锁、依赖熔断、安全错误分类及 correlation/traceparent 传播。 | `reliability_service.py`、`request_context.py`、`test_reliability_service.py` |
| FR-14 | README、上游归属、NOTICE、SECURITY、ADR、Compose、Demo、CI 和公开前检查完整保留。 | `README.md`、`.github/workflows/`、`docs/` |
| FR-15 | 版本化 Business Skill Catalog 声明角色、Schema、工具、前置状态、预算、版本和 Eval 引用。 | `skill_catalog.py`、`tool_registry.py`、`test_skill_catalog.py` |
| FR-16 | Schema/Evidence/Tool 失败时至多一次受限结构化校正；RunManifest 仅支持合成/Mock/只读回放，禁止业务写入。 | `structured_output_gateway.py`、`rag_evidence_verifier.py`、`test_structured_output_gateway.py` |
| FR-17 | 客户只能提交 helpful/not_helpful 与闭集 reasonCode；人工审核后才可形成合成候选，绝不直接训练或改策略。 | `CustomerFeedbackRequest`、`feedback_governance_service.py`、客户路由/前端 |
| FR-18 | 预算、锁、熔断、跨服务 correlation、本地指标与 AI Coding 质量门禁。 | `reliability_service.py`、`llm_observability.py`、`AGENTS.md`、CI workflow |
| FR-19 | Java 确定性人工案件队列、领取、补件、核验、处理、结案、版本/幂等/Outbox 和客户公开进度。 | Java `AiServiceCaseServiceImpl`、`AiServiceOperationsServiceImpl`、服务案件路由/测试 |

## 可见性、成本与失败回退

- 消费者仅看公开回答、来源名、Java 事实卡、草案、最终申请状态和本人案件进度；不会看到 Token、内部意图、完整 RAG passage、工具载荷、Trace、Outbox 或内部备注。
- 运营仅看最小 Handoff 和 Java 可信聚合；质量开发者仅看合成 EvalCase/Profile/RunManifest 安全投影；人工处理人员只看可领取或已领取的最小案件。四类身份不复用 Token 或写权限。
- 一次受限校正仅在 Schema、证据、政策版本或工具契约失败后发生；校正输入是 allow-list 错误码与安全投影。第二次失败、模型不可用、Redis/Java/RAG/队列依赖异常或预算耗尽时安全停止，不调用 Java 写接口。
- `contract_mock`、RAG Chunk 与本地检索评测不调用外部模型；真实模型只在客户实际问题或显式 `live_model_synthetic` 下调用。本轮的 `live-model-synthetic.v1` 已以 3 条合成案例通过，Provider 未返回可用 Token 数；客户请求绝不等待完整评测集。

## 本轮已验证与未验证范围

完整命令、通过数量、Docker 网站代理结果、真实模型合成评测和本机 RAG 指标见 [TEST_AND_DEMO_EVIDENCE.md](TEST_AND_DEMO_EVIDENCE.md)。当前仍不能声称：真实支付/仓储/物流/维修接入、生产吞吐/SLA、真实用户数据或模型对所有自然语言输入的准确率。远程 GitHub Actions 已在公开发布验证基线通过，具体运行链接见 [TEST_AND_DEMO_EVIDENCE.md](TEST_AND_DEMO_EVIDENCE.md)。

本轮开始前的受限源码快照为 `snapshots/final-upgrade-implementation-prechange-20260901-105000.zip`；快照排除了 `.env`、凭据、日志、虚拟环境、模型、向量索引与 Docker 数据。回退应使用源码版本和数据库备份，不保留双运行时路径。

人工协同网站代理 `verify_service_case_live.py` 已在本轮以进程内随机凭据完成：客户安全转接、Java 规则入队、人工处理人员领取、补件、结案、客户公开时间线和跨账号隔离均通过。演示账号密码仅在验收进程中存在，未持久化；本地 Docker/合成数据结果仍不代表生产上线。
