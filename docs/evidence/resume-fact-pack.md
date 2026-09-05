# Mall v3.0 简历事实包

生成日期：2026-09-05（Asia/Shanghai）  
事实基线：`7f9cfb2d5171a88b2f6c5714f965e528c2543cc5`  
分支：`main`  
仓库：`https://github.com/Eleven617/mall-ai-after-sales-platform`

这份文件只整理当前代码、当前提交、确定性测试和已有评测证据。它不把历史对话中的数字当作事实，不把本机结果写成生产能力，也不把上游 `macrozheng/mall` 代码写成个人原创。

## 当前版本状态

在本次核对开始时，`git status --short --branch` 为 `## main`，工作区干净；`git diff --stat` 为空；`git rev-parse HEAD` 为 `7f9cfb2d5171a88b2f6c5714f965e528c2543cc5`；`git remote -v` 指向 `Eleven617/mall-ai-after-sales-platform`。`origin/main...HEAD` 的提交计数为 `0 1`，即本地领先远程 1 个仅文档提交；本次没有提交或推送事实包。

业务/评测代码最后一次提交是 `38cf3809e48ec08bead6accc07a4ace27ebf5f59`，之后的提交只调整进度和证据文档。这个事实可以帮助理解代码没有改变，但按本任务的严格口径，任何报告若记录的 `testedCodeCommit` 不是当前 HEAD，仍必须标为 stale，不能当作当前 HEAD 的现场报告。

### stale 报告

| 报告 | 报告记录的提交 | 当前处理 |
| --- | --- | --- |
| `docs/evidence/v3.0-current-head-evidence.md` / `.json` | 业务提交 `38cf380`；证据提交 `94d7820` | stale。确定性结果已由本文件重新在 `7f9cfb2` 执行；live model 与 Grounding 数字仅保留为历史参考。 |
| `docs/evidence/v3.0-release-evidence.md` | 混合引用 `9fba15d`、`df67753`、`f88fee3` 等历史提交 | stale/历史记录，不与当前结果合并。 |
| `docs/TEST_AND_DEMO_EVIDENCE.md` | 包含多个日期和不同测试选择 | 历史证据索引，不是一份单一当前运行报告。 |
| `PROGRESS.md` | 2026-09-04 暂停点 | 进度记录，不作为当前测试结果。 |

## 项目事实

正式定位是“可信电商售后与 AgentOps 平台”，基于 Apache-2.0 的 `macrozheng/mall` 二次开发。目标用户和角色包括客户、运营分析人员、AI 质量开发者和人工售后处理人员。客户可以用自然语言咨询政策、查询订单/物流事实、发起或跟进售后；运营只读查看最小转接事项和聚合窗口；质量开发者运行版本化合成评测；人工处理人员处理受控案件。

它与普通 Chatbot 的差别在于：LLM 只能在结构化 Schema、Skill 白名单、预算和身份范围内形成计划或草案；Java `mall2/` 负责 JWT、订单/物流/资格/售后事实、状态机、幂等、事务、审计、Outbox 和最终写入；需要副作用的 `draft`、`commit`、`async_task` 必须先形成服务端 ActionProposal，客户确认后才调用 Java。FastAPI 不直连商城业务数据库，RAG 只提供政策证据。

## 架构和真实代码位置

| 能力 | 真实位置 | 当前事实 |
| --- | --- | --- |
| 客户/Agent Task API | `mall-ai-service/app/routers/agent_tasks.py` | `/agent-tasks` 创建、继续、动作确认、事件查询和有限 SSE 快照；公开 DTO 不含内部任务载荷。 |
| Agent Runtime | `mall-ai-service/app/runtime/task_runtime.py`、`task_store.py`、`task_planner.py` | 有界计划、Skill 发现、只读观察、Context 更新、ActionProposal、确认门和 owner 访问控制。 |
| Context/Memory | `app/runtime/context_curator.py`、`task_memory.py`、`app/schemas/agent_task.py` | 只处理允许的 Artifact 摘要；记忆有 owner/task 范围和 TTL；完整原话、Token、原始工具载荷不进公开状态。 |
| Critic | `app/runtime/resolution_critic.py` | 只在条件触发时给方案缺口/排序建议，不能提交业务动作；本次 live 报告中 Critic 调用为 0。 |
| Skill/Tool | `app/skills/catalog.py`、`commerce_gateway.py`、`tool_registry.py` | Catalog 是唯一能力来源，服务端校验 Skill 版本、输入输出 Schema、owner、预算、超时和允许工具。 |
| Trace/Eval | `app/services/trace_service.py`、`app/runtime/release_evaluation.py`、`scripts/run_quality_agent_evaluation.py` | Trace 为 `trace-v2` allow-list 元数据；质量评测使用版本化合成 Case 和确定性比较器。 |
| 统一售后 | `app/routers/customer_service.py`、`app/services/customer_service.py`、`unified_after_sales_graph.py`、`after_sales_application_service.py` | 政策、资格、申请、列表、状态、取消、修改、跟进；写操作经过 proposal/confirmation/Java。 |
| RAG | `app/services/chunking_service.py`、`policy_retrieval.py`、`rag_service.py`、`rag_evidence_verifier.py`、`app/services/vector_store.py` | 本地 Embedding/Chroma + BM25/RRF/可选 Cross-Encoder；metadata 过滤由服务端事实提供；无证据安全拒答。 |
| Java 权威层 | `mall2/mall-portal/.../AiAfterSalesApplicationServiceImpl.java`、`AiCaseHandoffServiceImpl.java`、`AiAfterSalesOutboxPublisher.java`、`AiAfterSalesFulfillment*` | 归属、状态、幂等、事务、Outbox/RabbitMQ 和最终写入。真实支付、仓储、物流、维修系统未接入。 |
| 运营/人工/质量边界 | `mall2/mall-admin/.../AiServiceOperationsServiceImpl.java`、`AiAfterSalesReviewServiceImpl.java`；`mall-ai-web/src/OperationsPanel.vue`、`QualityPanel.vue`、`AgentTaskWorkspace.vue` | 独立角色和公开投影；质量页只运行合成评测，不读真实客户聊天或生产 Trace。 |
| MCP | `mall-ai-service/app/routers/mcp.py`、`schemas/mcp.py` | 认证 Streamable HTTP/SSE 只读工具；禁止写操作、任意 URL、身份范围和 SQL 参数。 |

## 技术栈和边界

- Java / Spring Boot / MyBatis：商城领域事实、权限、事务和最终写入。
- FastAPI / Pydantic / LangGraph 适配层：受控 Runtime、售后编排、Schema、RAG、Redis 会话和评测。
- Vue 3 / TypeScript：客户、运营、质量和人工处理页面，只消费安全公开 DTO。
- MySQL：Java 业务数据；Redis：会话、短期锁、待确认状态和限流；Mongo：v3 Runtime 任务索引；RabbitMQ + MySQL Outbox：异步事件。
- 本地 BGE Embedding、Chroma、BM25、RRF、可选 Cross-Encoder：政策检索实验。当前默认 Dense；Hybrid/Rerank 不因“技术更全”上线。
- Docker Compose：本地完整演示。GitHub Actions：Python、Java、Web、Compose contract、质量评测和安全扫描门禁。

## 当前 HEAD 的确定性测试

以下命令均在 `7f9cfb2d5171a88b2f6c5714f965e528c2543cc5` 执行，退出码均为 `0`。测试数据是版本化合成 fixture；结果互不相加。

| 套件 | 命令 | 结果 |
| --- | --- | --- |
| FastAPI 回归 | `Push-Location .\\mall-ai-service; .\\.venv\\Scripts\\python.exe -m pytest -q; Pop-Location` | `349 passed`，1 条第三方弃用警告，7 个参数化子断言；17.92s。 |
| v3 manifest | `python scripts/validate_v3_release_manifest.py --json` | `478` deterministic、`36` live、`12` performance profile；manifest/case hash 通过。 |
| v3 preflight | `python scripts/run_v3_release_preflight.py --json` | `478/478` deterministic，代表性 Runtime `8/8`，失败 0。 |
| Quality Agent contract_mock | `python scripts/run_quality_agent_evaluation.py` | `17/17 passed`。 |
| Task orchestration contract_mock | `python scripts/evaluate_task_orchestration.py --mode contract_mock` | `11/11 passed`，environment_blocked `0`。 |
| Chunk/Metadata | `python scripts/evaluate_chunk_metadata.py --summary` | `8/8 passed`，合成 chunk `5`，外部模型调用 `0`。 |
| RAG 2.0 | `python scripts/evaluate_rag2.py --summary` | Dense/Hybrid/Hybrid+Rerank 各 `52/52`；Dense MRR `0.948718`、nDCG@3 `0.962147`；Rerank p95 `2817.72ms`。 |
| Java portal | `mvn -pl mall-portal -am '-Dtest=AiCaseHandoffServiceImplTest,AiServiceCaseServiceImplTest,AiServiceCaseOutboxPublisherTest,AiServiceCaseEventReceiverTest,SpringDataWebExposureContractTest,MongoMicrometerCompatibilityTest' '-DskipTests=false' '-Dsurefire.failIfNoSpecifiedTests=false' test` | `14/14 passed`，失败/跳过 `0`，BUILD SUCCESS。 |
| Java admin | `mvn -pl mall-admin -am '-Dtest=AiServiceOperationsServiceImplTest,AiServiceOperationsControllerTest' '-DskipTests=false' '-Dsurefire.failIfNoSpecifiedTests=false' test` | `6/6 passed`，失败/跳过 `0`，BUILD SUCCESS。 |
| Web | `Push-Location .\\mall-ai-web; npm run build; Pop-Location` | `vue-tsc --noEmit` 和 Vite production build passed。 |
| Compose contract | `docker compose --env-file .env.example config --quiet` | passed；未启动/删除容器。 |

## RAG、模型和现场证据

52 条版本化 RAG 黄金集在当前本机重新运行：三种模式均 `52/52`。Dense 的排序指标最高，因此保留默认；Hybrid/Rerank 只作为可复现实验。该结果只说明当前小型合成政策语料和本机环境。

历史 live model 开放任务报告 `tmp/live_model_agent_runtime_report_current_head.json` 的 SHA-256 为 `20e82406f4f8eceaf722dfc13249fe08f3d13e31b64eb791c122c54c7f112e0b`，记录提交不是当前 HEAD，必须标为 stale：24 个独立案例 × 3 次，共 72 次，`24 passed / 48 failed / 0 environment_blocked`；任务完整完成 `46/72`，澄清正确 `62/72`，必要 Skill/事实覆盖 `29/72`，Proposal/恢复 `56/72`，禁止副作用 `0`，重复最终业务写入 `0`，端到端 p50/p95/max 为 `3282/7859/10219ms`，总 token `333383`，成本 unavailable。失败包括 `required_skill_or_fact_missing`、`terminal_status_mismatch`、`runtime_exception_validationerror`、`unsafe_no_evidence_or_failure_continuation`、`proposal_or_resume_missing`、过期 proposal、重复确认和无关 Skill 调用。这组数据只用于面试中的失败分析，不能写成当前 HEAD 的模型准确率。

历史 Grounding 报告 `tmp/rag2_grounding_current_head.json` 的 SHA-256 为 `f254dea3c765251ae49385a3f6c1fd93276b474717f040557b8c7a57093cf0be`，同样 stale：15 条中 `11 passed / 4 quality_failed / 0 environment_blocked`，通过率 `0.733333`；4 条均为 `UNAPPROVED_EVIDENCE_SOURCE`。它说明证据来源门禁仍有待修复，不应合并成“RAG 回答正确率”。

浏览器 E2E、Java/MySQL 集成、故障注入和 durable async recovery 的 manifest 注册数量分别为 `24/30/36/32`，当前没有逐条现场执行证据，不能把注册数当成通过数。真实支付、仓储、物流、维修、生产 SLA/告警也未接入。

## 贡献和上游边界

`mall2/` 源于 `macrozheng/mall`，订单、会员、基础商城结构和部分 Spring/MyBatis 代码属于上游基础。本项目新增或集成的重点是 AI 售后入口、受控 Task Runtime、统一售后编排、RAG/证据核验、Skill Catalog、Trace/Eval、MCP 只读边界、Java 事实投影、人工案件、幂等 Outbox/RabbitMQ、Vue 角色页面和证据化交付。准确分工见 `docs/CONTRIBUTION_MATRIX.md`、`UPSTREAM.md` 和 `NOTICE`。

AI 编程辅助参与了代码检索、实现草案、测试设计、文档和本地验证编排；人工负责产品范围、权限与隐私、Java 写入权威、幂等/消息语义和最终验收。不能声称个人独立完成整个 Mall，也不能把 AI 生成草案未经审阅的内容当作个人原创设计。

## 可以写进简历的事实

1. “基于 Apache-2.0 `macrozheng/mall` 二次开发可信电商售后与 AgentOps 平台，Java 负责事实、权限、状态机、幂等、事务和最终写入，FastAPI 负责受控 Agent Runtime、RAG、Skill 和评测。”证据：`docs/architecture.md`、`docs/CONTRIBUTION_MATRIX.md`；当前 HEAD；置信度高；不能扩大为独立原创商城或生产 SaaS。
2. “实现版本化 v3 Release Manifest 与确定性 preflight，478/478 deterministic Case、8/8 代表性 Runtime 分支通过。”证据：本文件当前 HEAD 运行、`evals/v3/release-manifest.json`；manifest SHA `d9fc72be...2ac1ad`、case SHA `18a3ad20...938ccd`；置信度高；不能写成 478 条真实用户任务。
3. “建立受限 Agent Runtime：计划、版本化 Skill 发现、只读事实调查、Context Pack、owner 隔离和 ActionProposal/确认门。”证据：`app/runtime/task_runtime.py`、`task_store.py`、`app/skills/catalog.py`、`app/schemas/agent_task.py`；当前 HEAD FastAPI `349 passed`；置信度高；不能写成通用自治 Agent 或自动退款。
4. “构建政策 RAG 2.0 评测链路，在 52 条版本化合成黄金集上对比 Dense、Hybrid 和 Cross-Encoder Rerank，并保持 Dense 为默认。”证据：`scripts/evaluate_rag2.py`、`mall-ai-service/evals/rag2_golden_cases.v1.json`；SHA `632f36c3...a4fcc1`；当前结果三模式 `52/52`；置信度高；不能写成生产准确率或成本下降。
5. “用 allow-list Trace、Quality Agent contract_mock 和任务编排合同测试覆盖模型不可用、越权、工具失败、非法结构化输出和重复调用等安全边界。”证据：`app/services/trace_service.py`、`scripts/run_quality_agent_evaluation.py`；Quality `17/17`、Task `11/11`；置信度高；不能声称完成全部现场故障恢复。
6. “Java portal/admin 定向协同与运营测试分别 14/14、6/6 通过，Web production build 通过。”证据：本文件命令和 `mall2/.../src/test`；当前 HEAD；置信度高；不能扩大为 Java/MySQL 全量集成或生产部署。

## 只能用于面试材料的内容

- stale live model synthetic：24/72 通过、任务完成 `46/72`、澄清 `62/72`，适合讲如何从失败类别定位 Runtime/Schema/工具规划问题。
- stale Grounding：11/15 通过、4 条 `UNAPPROVED_EVIDENCE_SOURCE`，适合讲证据核验与拒答边界。
- 历史 Docker 8/8 healthy、endpoint 3/3、真实页面截图和历史 GitHub Actions success；它们对应旧提交/旧现场，不是当前 HEAD 的远程验证。
- 任务感知对话、统一售后八类动作、MCP 只读、Outbox/回调、人工协同等架构设计，适合结合真实文件解释，不能把未逐条现场执行的 manifest 场景说成全量通过。

## 不能宣称的内容

- 当前 HEAD 已通过 GitHub Actions；当前 HEAD 尚未推送，最近成功 Actions 对应旧提交 `94d7820`。
- 生产准确率、真实用户泛化、生产 SLA、QPS、成本下降、线上告警或真实外部履约成功。
- 24 条浏览器 E2E、30 条 Java/MySQL 集成、36 条 fault injection、32 条 durable async recovery 已全部现场通过。
- 真实支付、仓储、物流、维修系统已经接入。
- 个人独立完成 `macrozheng/mall` 上游商城代码。

## 复核限制

本事实包没有修改业务代码、测试、依赖、配置，也没有提交或推送。确定性测试使用本机环境；live model/Grounding 报告因提交不一致标为 stale；成本因 provider 未配置计价不可用；完整浏览器、跨服务集成和故障恢复仍需要在具备一次性合成账号/订单和可控现场的环境中单独运行。
