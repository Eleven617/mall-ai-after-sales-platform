# 测试、评测与现场证据

## 当前候选快照｜v3.0.4 最终在线批次后（2026-09-22）

Runtime/image `d4ec989548e953a8f8c5ee7ceef4ea13b464fbfb`：FastAPI **510/510**（494 cases + 16 subtests）、manifest **478/478**、representative **8/8**、contract replay **36/36**。

同一镜像从 0/122 完整现场通过 Browser 24、Java/MySQL 30、隔离 Compose Fault 36、Durable Recovery 32；failed=0、environmentBlocked=0。有效报告 SHA-256 `c29bc370c79a9235f7aa5ab7e7cdb50d2558bec5037123e2a1fb8088fafb244e`，Fixture SHA-256 `a7bd88ba4340e8116d1672e40a00caede1bc4621894952e36de508a673efcb95`，Provider requests/tokens=0/0。

当前镜像现场 **122/122**，报告绑定 Runtime `d4ec989`、execution HEAD `25d9150`，Provider 0/0。最终在线批次固定评测 `5/5`：普通 Agent `1/1`、Grounding `4/4`；16 attempts 全部成功、42,123 tokens、Ledger reconciled。首条 live 售后链业务断言通过，其原任务页面已零模型事后补采；其余两条当前 live 链未执行。当前 deterministic 展示链 **3/3**、12 帧另行标注。Release Gate **NOT_COMPLETE**。

## 当前候选快照｜v3.0.4 最小在线复测取证（2026-09-21）

Release `mall-v3.0.4-minimal-retest-78c7dd5-20260921` / Batch `minimal_retest-d551e9d01402` 已执行，状态 **NOT_COMPLETE**：逻辑请求/HTTP attempts 21/21、成功 19、网络失败 2、Token 73,833，reservation/settlement 21/21、Ledger reconciled。三条展示链业务断言通过，但目标及对照评测 11 Case 全部 `not_executed`；素材跨场景复用了 evidence/handoff/status 帧，不是可发布证据。

离线修复 Runtime `e1df8c4266f676330cb4c581a0c105dab10932a7` 的 FastAPI JUnit **477/477**（461 cases + 16 subtests），manifest **478/478**、representative **8/8**、contract replay **36/36**。旧现场 **122/122** 绑定 `78c7dd5`，不绑定新 Runtime。本轮新增 Provider 请求/Token 为 0/0；详情见 `docs/evidence/v3.0.4-minimal-retest-forensic-analysis.md`。

## 当前候选快照｜v3.0.4 最小在线复测前冻结（2026-09-21）

Runtime `78c7dd5c0156d7d4b18df75b0df6221b6b2b4df4`，执行 HEAD `2ec1de88e235de57cebefcaa266db9a02c6e8502`。FastAPI JUnit **473/473**（457 pytest cases + 16 subtests），manifest **478/478**、representative **8/8**、contract replay **36/36**，语义审计为 0。当前镜像现场从零通过 **122/122**，failed=0、environmentBlocked=0；报告 `tmp/v304-field-acceptance-78c7dd5/field-20260921T081500Z-e650ac28/field-acceptance.json`，SHA-256 `b03b6cee49951b301e13dc38531834cb65e210df0d351f6d659c74bd55cf18ec`。本轮外部 Provider requests/tokens 为 0，当前 SHA 远程 CI pending，最小在线复测 `not_run_by_design`，发布状态 **NOT_COMPLETE**。

## 当前权威快照｜v3.0.4 唯一正式在线批次（2026-09-20）

无模型预检和当前离线门禁通过后，唯一正式 Batch `portfolio_final-3d7b9340d60d` 在 Provider 网络前因 Ledger 初始化缺陷作废；根因分类为 `release_infrastructure_failure`，`task_terminal_state_unexpected` 仅为 Runner 表象。逻辑 Provider 请求 1、实际 HTTP attempts 0、Token 0；Proposal、Skill/Tool 调用、Java 资格核验、最终写入和状态回查均为 0。主集、补充集、Grounding、另两条展示链和 live 素材全部 `not_executed`，没有单 Case 重试。

当前 Release 为 **NOT_COMPLETE**。FastAPI **455/455**、manifest 478/478、contract replay 36/36 和现场 122/122 是本地合成 deterministic/offline 工程证据，不能写为真实模型准确率或生产能力。

## 当前权威快照｜v3.0.4 在线入口预检修复（2026-09-19）

当前 Runtime 候选 `3c4c3a5ae9fac944350b6710322fd9d5223eccde` 的正式在线入口新增无模型预检：检查进程级 `MALL_LIVE_DEMO_PASSWORD`（缺失时仅在进程内生成临时合成密码），并仅通过本地 Java API 创建/登录合成账号；预检通过前不会创建 Release/Batch、Ledger、Lock 或报告。

FastAPI 为 **450/450**（438 pytest cases + 12 subtests），预检回归 **19/19**；manifest 478/478、代表性 8/8。本轮 Docker/Java 现场因执行环境权限阻塞，当前 Runtime 的现场结果未启动，历史 122/122 不能合并。Provider requests=0、Token=0，发布状态 **NOT_COMPLETE**。

## 当前权威快照｜v3.0.4 离线候选（2026-09-18）

候选分支 `codex/v3.0.4-eval-contract-alignment`，Runtime Freeze `267e3b70e73cedb4ff714857a2195d56d4799161`。FastAPI 终端为 **432 passed + 12 subtests**，JUnit **444/444**、0 failed、0 skipped；manifest **478/478**、代表性 **8/8**；Java 定向测试、Vue build 与 Compose config 均通过。

当前现场 Runner 从零执行并通过 **122/122**：Browser **24/24**、Java/MySQL **30/30**、Fault Injection **36/36**、Durable Recovery **32/32**，failed=0、environmentBlocked=0。报告 `tmp/v304-field-acceptance-v267-livefault/field-20260918T113619Z-83fcab68/field-acceptance.json`，SHA-256 `4db9cca31a2ab77af02f2ddf9892a933ab75821c431df268ae10e89ecad8b2a9`；Fixture SHA-256 `7573e19271528e904d2eb40cef2765f05d4e5f489f2b35cc1b1359bcd5128759`。Docker 主栈 8/8 healthy，AI Runtime image revision 为该 Freeze。

本候选 **NOT_COMPLETE**：DeepSeek `not_run_by_design`，calls=0、Token=0，未创建在线 Release/Lock。当前 SHA 的 CI 为 `pending_remote_final_sha`；下一步只等待一次单独授权的正式在线批次。确定性与合成现场结果不能表述为 Grounding、真实模型准确率、生产 SLA 或真实用户泛化。

## 当前权威快照｜v3.0.2 离线候选（2026-09-15）

当前状态：**NOT_COMPLETE（离线条件与远程 CI 已满足，在线批次待单独确认）**。冻结 SHA `061d60bb13004dc7df57a161b01e378335f8938c`；FastAPI **399/399**（0 failed、0 skipped，机器报告）；Java portal/admin/Spring **14/14、6/6、1/1**；Vue build passed；manifest/preflight **478/478、8/8**；RAG 合同 **21/21**。证据提交 `dc7dee733ed056af054450df9b1399e199812539` 的 [`mall-ci`](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34978867905) 与 [`quality-evaluation`](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34978867657) 均成功。

冻结 SHA 的 122 条本机现场 Runner 全部通过：browser 24/24、Java/MySQL 30/30、fault 36/36、durable 32/32，`environment_blocked=0`，Fixture SHA `ba77efdd1b2112d2a2dc50561cb3d7fcd041a48d07a00e7bf7611fac103cab6d`。公共 Nginx 慢调用为 76.125 秒、HTTP 201、`ready_to_commit`，无 Provider 请求和 Java 写入。deterministic/replay 展示链各 3/3、各 12 帧。

本轮不调用 DeepSeek 或其他外部模型；真实模型泛化、生产 SLA、真实支付/仓储/物流/维修履约仍未验证。v3.0.1 历史失败锁定为 `gateway_timeout_before_agent_completion`，不与本轮离线结果合并。

## 当前权威快照｜v3.0.1 最终在线验收（2026-09-15）

代码冻结 `06ef600e51e7b0dc362d43a98e274c28144738d8`。FastAPI **382 passed**、deterministic **478/478、8/8**、Vue build、Java portal **14/14** + Spring context **1/1**、当前本机合成现场 **122/122** 通过。唯一正式 DeepSeek candidate `candidate-226cdd440e85` 在 `main_open_task_closed_loop` 展示链失败后锁定，main/supplemental/Grounding 未执行，当前 Release Gate **NOT_COMPLETE**。

候选报告 SHA-256 `6615d069122cb66ee8f3467f98ae79457ef287afd6f19c5e56035c45fb0b65c8`；共享 ledger 观察 9 次 Provider 请求、9 成功、0 失败、27,329 tokens，但这不代表模型任务准确率。现场报告 SHA-256 `ec337708baa422fcd11bf2ac2334372e88f3592f4dde454ab0f674413704122b`。提交 `5629f7b` 已推送；quality-evaluation 成功，mall-ci 在 `public-release` 因历史 FastAPI 381 断言失败，旧运行不能替代。

## 当前权威快照｜v3.0.1 候选验收（2026-09-14 UTC）

当前发布状态：**NOT_COMPLETE**。

运行时代码：`54de463b4990229b591e1fd0a278f754bf240678`。FastAPI **381 passed**、12 个子断言；deterministic **478/478、8/8**；Compose 配置检查通过；Browser 24/24、Java/MySQL 30/30、Fault 36/36、Durable 32/32，`environment_blocked=0`。本轮不调用 DeepSeek；deterministic/replay 展示链与 Java 写入回查均通过。实时 Grounding 未运行，旧模型报告与当前 Runtime 不一致，统一标记 stale。

原始报告路径、退出码和 hash 见 [`current-release-facts.json`](../evidence/current-release-facts.json) 与 [`v3.0.1-offline-and-live-acceptance.md`](../evidence/v3.0.1-offline-and-live-acceptance.md)。提交 `5bfdc3c` 的 `mall-ci` 与 `quality-evaluation` 已实际 success；新候选锁已写入 `deepseek-release-lock-v3.0.1.json`，不再重跑。

本轮提交 `bd3a5cf` 的远程 `mall-ci` 与 `quality-evaluation` 均为 success：[`mall-ci`](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34931831197)、[`quality-evaluation`](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34931831222)。

## 历史审计记录（以下内容不代表当前 Commit）

## 2026-09-12 当前代码补测

当前运行时代码：`52d5482455e2389cfd6c2ef15d233712607ffa9f`。FastAPI **362 passed**；live model main **72/72**、holdout **36/36**；Grounding **15/15、57/57 checks**；v3 deterministic **478/478、8/8**；Java portal/admin **12/12、6/6**；Vue build 通过；本地四类现场 Runner **122/122**。原始报告和 hash 见 [`final-agent-quality-baseline.md`](../evidence/final-agent-quality-baseline.md)。旧数字如与本节冲突，按 stale/superseded 处理。

## 证据原则

每个结果都绑定命令、退出码、运行模式、Commit、Fixture/报告 hash 和限制。确定性合同、真实 Docker 现场、合成模型评测和远程 GitHub CI 分开统计，不能相加。

## 最新现场报告

| 字段 | 值 |
| --- | --- |
| 报告 | `tmp/field-acceptance/field-20260909T105750Z-12222b15/field-acceptance.json` |
| 报告 SHA-256 | `6a301cd28072ebbf01fa07e81d7aaf5c4b2de9741c14ceb351122cac18f21567` |
| Fixture SHA-256 | `7573e19271528e904d2eb40cef2765f05d4e5f489f2b35cc1b1359bcd5128759` |
| 运行时代码 | `84e111d17e4117287660421ea5772a9ddcf44382` |
| Docker | Engine `29.7.2`；Compose 配置有效；主/隔离项目健康 |
| 结果 | 122 executed，122 passed，0 failed，0 environment_blocked |
| 总时长 | 211947 ms |

## 确定性与本机回归

| 套件 | 命令/模式 | 结果 | 能证明什么 |
| --- | --- | --- | --- |
| FastAPI | `mall-ai-service/.venv/Scripts/python.exe -m pytest -q` | 353 passed，7 子断言，1 warning，exit 0 | 当前 Python 合同/回归 |
| Runner 合同 | `pytest` 受影响 Runner 测试 | 11 passed，exit 0 | runner schema/断言完整性 |
| v3 manifest | `validate_v3_release_manifest.py --json` | 478/478 | 注册合同与白名单完整 |
| v3 preflight | `run_v3_release_preflight.py --json` | 8/8 | 确定性依赖前置 |
| quality-agent | `run_quality_agent_evaluation.py` | 17/17 | 质量 Agent 合同 |
| task orchestration | `evaluate_task_orchestration.py --mode contract_mock` | 11/11 | 任务感知/状态合同 |
| RAG verifier | `evaluate_rag_verifier.py` | 36/36（28 支持、8 无证据） | 证据支持/拒答硬规则 |
| chunk metadata | `evaluate_chunk_metadata.py --summary` | 8/8 | Chunk 契约/元数据 |
| Java portal | Maven，`-DskipTests=false` 定向套件 | 14/14 | Portal 业务/Outbox 相关单测 |
| Java admin | Maven，`-DskipTests=false` 定向套件 | 6/6 | 运营/案件相关单测 |
| Spring/MySQL | `MallPortalApplicationTests` + 临时 Compose 连接配置 | 1/1 | 本机 Java context 与 MySQL 连接 |
| Vue | `npm run build` | exit 0 | 前端生产构建 |
| Compose | `docker compose config --quiet` | exit 0 | 配置语法 |

## RAG 与模型评测

- 52 条版本化黄金集：Dense Recall@1 `1.0`、MRR `0.948718`、nDCG `0.962147`；Hybrid 为 `0.935897/0.952683`，Rerank 结果相近但延迟/复杂度更高，因此 Dense 保持默认。
- Grounding 合成评测：15 cases，11 passed、4 quality_failed（`UNAPPROVED_EVIDENCE_SOURCE`）；这不是生产准确率。
- live_model_synthetic 开放任务：24 passed、48 failed、0 blocked（每 case 多次运行）；只用于暴露模型/编排问题，不能推断自然语言泛化。
- 真实模型调用没有作为默认 CI 门禁；无 Key 或 Provider 不可用时应标记 `environment_blocked`，不能用 mock 数字替代真实效果。

## Build 14A

`tmp/run_build14.ps1` 调用 `verify_build14_eligibility_live.py`，最新退出码 `0`。负路径确认 Java 拒绝未收货订单，正路径经过运营发货与客户确认收货后创建申请；第二账号不可见、同幂等键不重复创建、事务 Outbox 存在。该验证使用真实 API 和本地合成数据，不直接改数据库。

## 远程 CI

当前基线 `5ea1199` 的 `mall-ci` 与 `quality-evaluation` 已真实 success；本次交接提交推送后必须再次确认与最终 SHA 对齐。CI 通过只证明工作流在 GitHub runner 上通过，不代表生产部署。

## 历史与限制

旧 Fixture 产生的阻断报告是 superseded；旧 Commit 的现场结果是 stale。历史 Build 21 曾出现等待任务缺失的独立重跑失败，已保留为运行时波动，不被隐藏。没有真实支付/仓储/物流/维修系统、生产告警、生产 SLA 或真实客户数据。
# v3.0.4 在线入口预检修复（2026-09-19）

当前 Runtime 候选 `3c4c3a5ae9fac944350b6710322fd9d5223eccde` 新增了无模型的正式在线入口预检。它先检查进程级 `MALL_LIVE_DEMO_PASSWORD`，再仅通过本地 Java API 创建/登录合成账号；只有预检成功，正式 Runner 才能生成 Release/Batch、Ledger、Lock 或调用 Provider。

- 预检回归：19/19；覆盖缺失 Secret fail-closed、Fake Java 合成账号预检、失败不创建 Lock/报告/账本、Secret 不进入错误文本、PowerShell/Compose/Python 变量名一致，以及正式单批次入口合同。
- FastAPI：JUnit 450/450（438 pytest cases + 12 subtests），0 failed、0 skipped；exit 0。
- Provider：0 requests，0 Token；没有新 Release、Batch、Ledger、Lock 或在线报告。
- 现场 122：当前 Runtime 尚未运行。此前 122/122 是旧 Runtime 的 deterministic/offline 报告，不计入本候选；本机 Docker CLI/Engine 与 Java 端点拒绝访问，状态为 `ENVIRONMENT_BLOCKED_DOCKER_JAVA`。

历史失败证据保持不变。本文件以下章节是历史审计记录，不能与上面的当前统计合并。
