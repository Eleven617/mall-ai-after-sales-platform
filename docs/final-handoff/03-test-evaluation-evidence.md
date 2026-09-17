# 测试、评测与现场证据

## 当前权威快照｜v3.0.3 Proposal 确认执行合同（2026-09-17）

候选分支 `codex/v3.0.3-confirmation-contract`，Runtime Freeze `db3860701086bf9718ac23ef7b272a28bff2083f`。Proposal-to-Commit 映射、版本化草案、人工协同确认、确认时事实/hash/owner/TTL 重校验和 Runtime 幂等键均有覆盖；FastAPI 终端 **415 passed + 12 subtests**，JUnit **427/427**；manifest **478/478**、代表性 **8/8**；Task 11/11、Quality 17/17、Dense RAG 52 条检索评测；Java 定向测试、Vue build、Compose 8/8 healthy。

本机合成现场 Runner **122/122**（Browser 24、Java/MySQL 30、Fault 36、Durable 32，0 failed/0 blocked）；版本化草案与人工协同现场链通过。现场报告 SHA `c975374fa6c9f6484063779be62e1cde6be499f5f3f397275f27e89c20c0e6cd`，FastAPI 语义报告 SHA `8698f94d3f13e070cb4ca9a71a8ad1eef024483ec64008918ea86549dd95b3f2`。

本候选 **NOT_COMPLETE**：唯一授权的正式批次 `mall-v3.0.3-portfolio-final-db3860701086` 在 `main_open_task_closed_loop` 的 `agent_task_create` 因 `scenario_assertion_failure` 停止。Provider 8/8 成功、29,542 Token、Ledger 对账通过，却未形成 Proposal，Java 核验/写入/回查均为 0；另两条核心链、主集、补充集、Grounding、素材均 `not_executed`。这不是 `environment_blocked`，且不得重跑。gitleaks 本机缺失仍为 `environment_blocked`；候选 `8f109ee` 的 CI 双绿，失败证据提交需以新 SHA 重新核对。不得把离线验收当成 Grounding 通过、在线批次或模型准确率。

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
