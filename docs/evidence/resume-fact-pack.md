# Mall AI 售后平台｜简历事实包

## 当前事实快照｜v3.0.3 Proposal 确认执行合同（2026-09-17）

当前候选分支 `codex/v3.0.3-confirmation-contract`，Runtime Freeze `3a0d59080e94848553ac2d981116acf236df3cf6`，发布状态 **NOT_COMPLETE**。本轮真实完成的是版本化 Proposal→Commit 映射、草案修改、旧版本冲突拒绝、人工协同确认与 Runtime 幂等键；FastAPI 终端 **411 passed + 12 subtests**（JUnit **423/423**）、manifest 478/478、现场 Runner 122/122、Java 定向测试、Vue/Compose 均通过。

本机现场均使用合成数据：Browser 24、Java/MySQL 30、Fault 36、Durable 32；草案修改链确认前 Java 写入 0、旧版本确认 409、当前版本写入 1、重复确认写入 0；人工协同链确认前写入 0、跨账号确认 404、确认后创建 1、重复确认 0。本次验证 Provider 0。报告与 hash 见 [`v3.0.3-capability-completion.md`](v3.0.3-capability-completion.md)。

注意：历史 grounding CLI 的 16 次 DeepSeek 调用仍标记 `invalidated_offline_run`，没有 Release ID/Lock，不能计入模型通过率；因此 `V3_0_3_LIVE_READY=false`。本机 gitleaks 为 `environment_blocked`，但提交 `697deab` 的 [`mall-ci`](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/35195018957) 与 [`quality-evaluation`](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/35195018813) 已成功。不能把本轮写成真实模型准确率、生产 SLA、真实外部履约或在线发布。

## 当前事实快照｜v3.0.2 离线候选（2026-09-15）

当前发布状态：**NOT_COMPLETE（离线候选与远程 CI 已通过，在线批次仍需单独授权）**；冻结运行时代码 `061d60bb13004dc7df57a161b01e378335f8938c`，分支 `codex/v3.0.2-offline-candidate`。证据提交 `dc7dee733ed056af054450df9b1399e199812539` 的 [`mall-ci`](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34978867905) 与 [`quality-evaluation`](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34978867657) 均为 success。

本轮可核验事实：FastAPI **399 passed / 0 failed / 0 skipped**；v3 deterministic **478/478**、代表性 Runtime **8/8**；Java portal **14/14**、admin **6/6**、Spring context **1/1**；Vue build 通过；本机合成现场 Runner **122/122**（browser 24、Java/MySQL 30、fault 36、durable 32）；公共 Nginx 慢调用 **76.125 秒、HTTP 201、ready_to_commit、Provider 0、Java 写入 0**；deterministic/replay 展示链各 **3/3**、各 12 帧。

这些结果分别属于机器可读合同、本地 Docker/Chrome/Java/MySQL/Redis/RabbitMQ 现场和零模型 deterministic/replay，不是生产 SLA、真实用户准确率或真实模型泛化率。在线 DeepSeek 本轮 `not_run_by_design`；v3.0.1 `gateway_timeout_before_agent_completion` 失败候选、9 次 Provider 观察与旧锁继续保留，未被改写。

## 当前事实快照｜v3.0.1 最终验收结果（2026-09-15）

当前发布状态：**NOT_COMPLETE**；运行时代码 `06ef600e51e7b0dc362d43a98e274c28144738d8`，分支 `codex/v3.0.1-offline-acceptance`。

可以如实写入简历/面试材料的当前事实：FastAPI **382 passed**、v3 deterministic **478/478**（代表性 8/8）、Vue production build、Java portal 14/14 + Spring context 1/1、当前本机合成现场 browser 24/24 + Java/MySQL 30/30 + fault 36/36 + durable 32/32（合计 122/122）。这些数字分别代表确定性合同、定向集成和本机合成现场，不代表生产 SLA 或真实用户准确率。

唯一正式 DeepSeek candidate `candidate-226cdd440e85` 已失败并锁定；共享 metadata-only ledger 观察到 9 次 Provider 请求、9 成功、0 失败、27,329 tokens，但 main 24×3、supplemental 12×3 和 Grounding 均未执行，不能写成模型任务完成率、泛化率或成本。候选报告与锁 hash 见 [`current-release-facts.json`](current-release-facts.json)。

当前不能写：真实模型自然语言准确率、生产部署/SLA/QPS、真实支付/仓储/物流/维修履约、模型成本、真实客户数据或把 `macrozheng/mall` 上游能力说成原创。远程推送本轮因 GitHub 443 超时未完成，旧 Actions 结果不替代当前 SHA。

## 当前事实快照｜最终公开收口

当前发布状态：**NOT_COMPLETE**。

运行时代码：`54de463b4990229b591e1fd0a278f754bf240678`；唯一事实源：[`current-release-facts.json`](current-release-facts.json)。当前可核验结果：FastAPI **381 passed**、12 个子断言、v3 deterministic **478/478**（代表性 8/8）、Compose 配置通过；浏览器现场 24/24、Java/MySQL 30/30、故障注入 36/36、Durable 32/32（`environment_blocked=0`）。本轮 DeepSeek 为 `not_run_by_design`，deterministic/replay 展示链通过但不证明真实模型泛化。

当前简历只能写受限 Agent Runtime、Java 权威事实与写入边界、版本化 RAG/grounding 设计和可审计合同门；不能把旧报告数字当作当前提交结果，也不能把合同数字写成生产准确率。基于 `macrozheng/mall` 二次开发，上游商城基础能力不归为原创。

## 历史审计记录（以下内容不代表当前 Commit）

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
