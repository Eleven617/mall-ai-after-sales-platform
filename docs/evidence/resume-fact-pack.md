# Mall AI 售后平台｜简历事实包

生成日期：2026-09-12（Asia/Shanghai）
运行时代码基线：`52d5482455e2389cfd6c2ef15d233712607ffa9f`
分支：`main`  
仓库：<https://github.com/Eleven617/mall-ai-after-sales-platform>

这份材料只使用当前代码、当前报告和可追溯命令。项目是基于 `macrozheng/mall` 的 Apache-2.0 二次开发；上游商城基础能力不归为个人原创。

## 推荐简历表述（可写）

1. **设计并实现受限开放任务 Agent Runtime**：以 FastAPI/LangGraph 组织目标理解、Skill 白名单、只读多步调查、Context 投影、ActionProposal 和确认边界；服务端验证 Schema、owner、预算和工具范围，当前代码基线 live synthetic 主集 72/72、holdout 36/36，禁止副作用与重复最终写入均为 0。
2. **建立 Java 权威业务边界**：LLM 不直接写商城库，订单/物流/资格/售后事实、JWT 归属、状态机、幂等、事务、Outbox/RabbitMQ 和最终写入由 `mall2/` 负责；本地现场 Runner 四类共 122/122 通过。
3. **构建版本化政策 RAG 与证据校验**：Dense 作为默认检索，Hybrid/Rerank 保留为实验；当前 grounding contract 15/15、57/57 checks，使用合成政策数据。
4. **搭建可审计评测与发布门禁**：FastAPI 362 passed，v3 deterministic 478/478、代表性 Runtime 8/8，Java portal/admin 定向 12/12、6/6，Vue production build 通过。
5. **完成本地容器化现场验收**：在 Docker/Chrome/Java/MySQL/Redis/RabbitMQ 与隔离 fault Compose 上运行 browser 24、Java/MySQL 30、fault 36、durable recovery 32，合计 122/122；报告绑定代码与 Fixture hash。
6. **补齐安全与证据化交付**：不提交 Key、密码、Token、客户原话、完整订单号或原始 Trace；README、测试证据、贡献边界和失败矩阵可追溯。

## 代码与架构定位

| 领域 | 真实位置 | 事实 |
| --- | --- | --- |
| Agent Runtime | `mall-ai-service/app/runtime/task_runtime.py`、`task_planner.py`、`task_store.py` | 有界计划、Skill/工具校验、Context、Proposal、恢复和失败停止 |
| Context/Memory | `app/runtime/context_curator.py`、`task_memory.py` | 只保存允许的 Artifact 投影、owner/TTL 范围，不保存完整原话/Token/原始载荷 |
| 售后 | `app/services/customer_service.py`、`unified_after_sales_graph.py`、`after_sales_application_service.py` | 八类动作；写操作 Proposal→确认→Java |
| RAG | `app/services/chunking_service.py`、`policy_retrieval.py`、`rag_evidence_verifier.py` | 版本化政策证据，Dense 默认，无证据停止 |
| Java 权威 | `mall2/mall-portal`、`mall2/mall-admin` AI 售后/案件服务 | JWT、归属、资格、状态、幂等、事务、Outbox、最终写入 |
| 前端 | `mall-ai-web/src` | 客户、运营、质量与人工处理安全 DTO，不持有内部 ID/Token |

## 证据与边界

- 主 live 报告：`mall-ai-service/tmp/final-agent-quality-main-final5-20260912.json`，SHA-256 `b4041b3541e125b48e4b1114ff1e100aeeb6c40bea29f426d048850414be87d2`。
- Holdout 报告：`mall-ai-service/tmp/final-agent-quality-holdout-final4-20260912.json`，SHA-256 `822775b454e921dc50817f764783ddd14fc65910e267b27aa2e559ecc5869612`。
- 现场报告：`tmp/field-acceptance-final/field-20260911T203212Z-95f5755e/field-acceptance.json`，SHA-256 `a0fbcd5c22638be8be480ae08344596a14d7874eafcd65194242b3f4df8c803e`。
- Fixture SHA-256：`d4829bd272dad498b17890b24595c288150ed89d4f59b062424b70067513e093`。

旧报告若绑定其他提交，均为 stale/superseded；旧失败不能从历史中删除。没有真实支付、仓储、物流、维修接入，也没有生产 SLA、真实用户泛化准确率、QPS 或模型成本结论。

## 面试追问准备

- 解释为何 Runtime 允许模型规划但不允许模型直接写库：Schema、Skill allow-list、owner/预算、Proposal/确认、Java 重读事实。
- 解释 478/478 与 122/122 的差异：前者 deterministic contract，后者本地 Docker/Chrome/Java/消息栈现场，二者都不是生产 SLA。
- 解释历史 70/72、71/72 失败如何转成通用修复：重复子任务、缺订单事实、Proposal 恢复后校验；修复后由回归和新 live 报告验证。
