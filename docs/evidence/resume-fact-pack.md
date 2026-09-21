# Mall AI 售后平台｜简历事实包

## 当前候选事实｜v3.0.4 最小在线复测前冻结（2026-09-21）

Runtime `78c7dd5c0156d7d4b18df75b0df6221b6b2b4df4`，发布状态 **NOT_COMPLETE**。本轮完成决策终态互斥合同、Prompt v3.4、Grounding 最小充分来源与 Durable Java/Redis 恢复屏障；FastAPI JUnit **473/473**（457 pytest cases + 16 subtests）、manifest **478/478**、contract replay **36/36**、当前镜像现场 **122/122**，Provider requests/tokens 均为 0。报告 SHA-256 `b03b6cee49951b301e13dc38531834cb65e210df0d351f6d659c74bd55cf18ec`。当前 SHA 的远程 CI pending，最小在线复测 `not_run_by_design`；历史在线评测与旧失败证据保持原样。

## 当前事实快照｜v3.0.4 唯一正式在线批次（2026-09-20）

当前候选 Runtime `3c4c3a5ae9fac944350b6710322fd9d5223eccde` 已完成离线工程验证，但唯一正式在线 Batch `portfolio_final-3d7b9340d60d` 在 Provider 网络前因 Ledger 初始化缺陷作废；公开根因分类为 `release_infrastructure_failure`，`task_terminal_state_unexpected` 仅为 Runner 表象。状态转换 `task_created -> task_blocked`；未形成 Proposal，Java 写入为 0。逻辑 Provider 请求 1、实际 HTTP attempts 0、Token 0，Ledger 对账通过；主集、补充集、Grounding 和其余在线链路未执行。

因此当前只能如实表述本地合成 deterministic/offline 验证（FastAPI 455/455、现场 122/122）和受控写入边界；不能写真实模型成功率、线上 SLA 或作品集已发布。发布状态 **NOT_COMPLETE**，不得重试本批次或创建第二批次。

## 当前事实快照｜v3.0.4 在线入口预检修复（2026-09-19）

候选 Runtime `3c4c3a5ae9fac944350b6710322fd9d5223eccde`，发布状态 **NOT_COMPLETE**。正式在线 Runner 在创建任何 Release、Batch、Ledger、Lock 或报告之前，先检查进程级 `MALL_LIVE_DEMO_PASSWORD`，再通过本地 Java API 验证合成账号创建/登录；Python、PowerShell 和 Compose 使用同一变量名，Secret 不写入公开工件。

FastAPI JUnit **455/455**（443 pytest cases + 12 subtests），0 failed、0 skipped；Ledger/Provider Guard 专项 **30/30**，manifest **478/478**、代表性 **8/8**。本轮没有新的外部 Provider 请求、没有新在线 Release 或第二批次。

## 当前事实快照｜v3.0.4 离线候选（2026-09-18）

候选分支 `codex/v3.0.4-eval-contract-alignment`，Runtime Freeze `267e3b70e73cedb4ff714857a2195d56d4799161`，发布状态 **NOT_COMPLETE**。FastAPI JUnit **444/444**（432 pytest cases + 12 subtests）；manifest 478/478、代表性 8/8、Java 定向测试、Vue build 与 Compose 配置通过。

当前合成本机现场从零执行 **122/122**：Browser 24/24、Java/MySQL 30/30、Fault 36/36、Durable 32/32，failed=0、environmentBlocked=0。报告 SHA-256 `4db9cca31a2ab77af02f2ddf9892a933ab75821c431df268ae10e89ecad8b2a9`，Fixture SHA-256 `7573e19271528e904d2eb40cef2765f05d4e5f489f2b35cc1b1359bcd5128759`；范围是 deterministic/offline Docker 现场，不是生产能力。

本轮 DeepSeek 为 `not_run_by_design`，calls=0、Token=0。仍不能写成真实模型准确率、生产 SLA、真实外部履约或线上 Release；旧在线失败批次仅保留历史审计，不能与当前结果合并。当前远程 CI 为 `pending_remote_final_sha`。

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
