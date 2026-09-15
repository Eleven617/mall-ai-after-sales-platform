# 公开发布记录

## 2026-09-15｜v3.0.1 当前 SHA 在线验收（最新权威）

运行时代码冻结 `06ef600e51e7b0dc362d43a98e274c28144738d8`，分支 `codex/v3.0.1-offline-acceptance`。离线 readiness 24/24 通过；当前 SHA 的本机合成现场 122/122 通过；唯一正式 DeepSeek candidate 失败并永久锁定，因此当前发布状态 **NOT_COMPLETE**。

| 门禁 | 当前结果 | 说明 |
| --- | --- | --- |
| FastAPI | **382 passed** | 本机 `.venv`，exit `0`，12 subtests |
| Java | **portal 14/14、Spring 1/1** | 显式 `-DskipTests=false`，Compose MySQL |
| Vue / Compose | **build passed；8/8 healthy** | `npm run build`、`docker compose config --quiet` |
| deterministic | **478/478；8/8** | contract_mock，无模型/业务写入 |
| 现场 Runner | **122/122 passed** | browser 24、Java/MySQL 30、fault 36、durable 32；合成数据 |
| DeepSeek candidate | **FAILED** | `candidate-226cdd440e85`，第一展示链失败；后续质量套件未执行 |
| GitHub Actions | **待当前 SHA 验证** | 本轮 GitHub 443 推送超时，旧 Actions 不并入 |

候选报告：`tmp/deepseek-v3.0.1-final-06ef600e51e7b0dc362d43a98e274c28144738d8.json`，SHA-256 `6615d069122cb66ee8f3467f98ae79457ef287afd6f19c5e56035c45fb0b65c8`；Release lock：`docs/evidence/deepseek-release-lock-v3.0.1-final-06ef600e51e7b0dc362d43a98e274c28144738d8.json`，状态 `FAILED`。共享账本只记录 9 次 Provider 元数据请求（9 成功、0 失败、27,329 tokens），这不是任务准确率或成本；报告/锁的 0 计数缺口已如实保留。

现场报告：`tmp/offline-field-acceptance/field-20260915T064300Z-99f3dc2f/field-acceptance.json`，SHA-256 `ec337708baa422fcd11bf2ac2334372e88f3592f4dde454ab0f674413704122b`。不生成 live GIF、不更新 README 为真实模型通过。不能宣称生产部署、生产 SLA、真实用户自然语言泛化、真实支付/仓储/物流/维修履约或模型成本。

## 2026-09-15｜冻结 SHA 验收记录（当前权威）

运行时代码冻结：`54de463b4990229b591e1fd0a278f754bf240678`；分支：`codex/v3.0.1-offline-acceptance`。本轮不调用 DeepSeek、不创建新付费模型批次；本地现场使用 deterministic/replay provider，并通过真实 Docker/Chrome/Vue/FastAPI/Java/MySQL/Redis/RabbitMQ 路径。

| 门禁 | 当前结果 | 范围 |
| --- | --- | --- |
| FastAPI | **381 passed** | 本机 `.venv`，exit `0` |
| Java | **portal 14/14、admin 6/6，编译成功** | 显式 `-DskipTests=false` |
| Vue | **production build passed** | TypeScript + Vite |
| deterministic manifest | **478/478；代表性 8/8** | contract only |
| 现场 Runner | **122/122 passed** | browser 24、Java/MySQL 30、fault 36、durable 32 |
| Agent showcase | **3/3 + 3/3** | `/agent-tasks` deterministic/replay，各 3 浏览器帧 |
| 新 DeepSeek / live grounding | **未运行** | 本轮明确禁止付费模型调用 |
| 当前发布资格 | **NOT_COMPLETE** | deterministic/replay 不等于真实模型泛化或生产发布 |

现场报告：`tmp/offline-field-acceptance/field-20260915T042914Z-8c8d67db/field-acceptance.json`，SHA-256 `c1e893c648ea6be102aef3f5c391a5dca28a220a4b2df80574e8bee4fd8b1223`；RAG 报告：[`rag2-retrieval-freeze-54de463.json`](evidence/rag2-retrieval-freeze-54de463.json)。本轮四类现场均 `environment_blocked=0`。任何绑定其他 Commit 的旧报告均为 stale/superseded，不与本次统计合并。故障组中 10 条为本地安全停止合同 + 隔离 Compose 重启，不是外部供应商中断证明。

本轮包含代码与证据的提交 `bd3a5cf787f87e2819c73021fc9a356c6c65da85` 的远程门禁：[`mall-ci`](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34931831197)、[`quality-evaluation`](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34931831222)，均为 success。

成本、生产 SLA、真实用户自然语言泛化、真实支付/仓储/物流/维修履约仍 unavailable/未接入；README 本轮不重写。

## 当前权威记录｜最终公开收口

更新时间：2026-09-14 UTC；运行时代码 `0162c4059c35211852f409a4c3517a87997b4f56`；分支 `codex/v3.0.1-offline-acceptance`。本节是当前唯一结论，后续旧日期内容均为历史审计，不能与本节合并统计。当前发布状态：**NOT_COMPLETE**。

| 门禁 | 当前结果 | 运行模式/边界 |
| --- | --- | --- |
| FastAPI | **376 passed**，0 failed | 本机 `.venv`，exit 0，1 warning、12 subtests |
| DeepSeek Batch 1 | **3/3 passed** | `deepseek-flash`、thinking enabled、reasoning high；11 次请求；合成 Runtime，只读网关 |
| v3.0.1 DeepSeek 候选批次 | **failed before quality suites** | `candidate-5f1d90208743`；真实展示阶段脱敏 ShowcaseError；0 requests/0 tokens；主集/补充/Grounding 未执行 |
| v3.0.1 现场门禁 | **browser 24/24；Java 30/30；fault 36/36** | 当前冻结 SHA、本机 Docker/Chrome/Java/MySQL 与合成 Fixture |
| Release lock | **locked / NOT_COMPLETE** | `docs/evidence/deepseek-release-lock.json`；同一 releaseId 再运行会在 Provider 前拒绝 |
| 补充评测集 | **未重跑 / stale** | 旧报告绑定旧 Runtime，不并入当前结果 |
| Grounding | **stale** | 旧报告绑定旧 Runtime |
| Java | portal core **12/12**、compatibility **2/2**、admin **6/6**、Spring **1/1** | 显式 `-DskipTests=false`；Spring 使用临时本地配置 |
| Vue | **production build passed** | `npm run build` |
| deterministic | **478/478；代表性 8/8** | contract_mock，不是 E2E |
| Durable live | **32 environment_blocked** | 运行它会在唯一正式批次外产生模型请求；确定性 durable contract 32/32 |
| 远程 CI | **mall-ci success；quality-evaluation success** | 提交 `5bfdc3c` 的 GitHub Actions 实际运行；不等于生产部署 |

事实源：[`current-release-facts.json`](evidence/current-release-facts.json)。公开演示素材和阻断记录：[`final-showcase-evidence.md`](evidence/final-showcase-evidence.md)。成本、生产 SLA、真实用户泛化和外部履约均 unavailable/未接入。

本次公开提交 `e0c8b36` 的首次远程 `mall-ci` 失败仅发生在 OSV：隔离扫描容器无法解析仓库内 Maven `1.0-SNAPSHOT` reactor 依赖，退出码 127；同一日志显示 0 个受影响包。修复提交 `0501d9d` 在保持 Java POM、OSV 扫描和风险例外可见的前提下增加 `--no-resolve`，其门禁通过；最终证据回填提交 `78c5c3c` 的两条远程门禁也均为 success。

## 历史审计记录（以下内容不代表当前 Commit）

## 2026-09-12｜最终收口复核（当前权威记录）

运行时代码基线：`52d5482455e2389cfd6c2ef15d233712607ffa9f`，分支 `main`。本节覆盖当前真实执行；下方旧日期内容仅作历史审计，不能覆盖本节或与其相加。

| 门禁 | 当前结果 | 证据 |
| --- | --- | --- |
| FastAPI | 362 passed，0 failed | `mall-ai-service/.venv/Scripts/python.exe -m pytest -q`，exit 0 |
| Live model synthetic | main 72/72、holdout 36/36 | DeepSeek + synthetic read-only gateway；无业务写入 |
| Grounding | 15/15，57/57 checks | `tmp/final-grounding-20260912.txt`，exit 0 |
| v3 deterministic | 478/478，代表性 8/8 | manifest/preflight，exit 0 |
| Java/Web | portal 12/12、admin 6/6、Spring 1/1、Vue build passed | 显式 `-DskipTests=false`；本地 Compose |
| 现场 Runner | 122/122，0 failed，0 blocked | 当前代码 + 合成 Fixture + Docker/Chrome/Java/MySQL/Redis/RabbitMQ |

当前本地合成 Release Gate：**passed**。证据提交 `efd3dcdd5d9c628a98b697ad63b57fe78b932cd9` 的远程 Actions 也已通过：[`mall-ci` run 34646346032](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34646346032)、[`quality-evaluation` run 34646346115](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34646346115)。它不是生产发布结论。没有接入真实支付、仓储、物流、维修；未宣称生产 SLA、真实用户泛化、真实成本或真实业务数据。

## 2026-09-09｜最终现场与 Release Gate 复核（最新权威记录）

当前远程 `main` 在证据复核开始时为 `5ea119970a2a4a9a9194dc3e1e46eff412bd406e`；该提交及本次后续提交只新增证据/交接文档，现场运行时代码仍绑定 `84e111d17e4117287660421ea5772a9ddcf44382`。Docker Engine `29.7.2` 可用，主 Compose 与隔离 fault Compose 均健康。

| 现场类别 | 实际执行 | 通过 | 失败 | environment_blocked |
| --- | ---: | ---: | ---: | ---: |
| browser_e2e | 24 | **24** | 0 | 0 |
| java_mysql_integration | 30 | **30** | 0 | 0 |
| fault_injection | 36 | **36** | 0 | 0 |
| durable_async_recovery | 32 | **32** | 0 | 0 |
| 合计 | **122** | **122** | 0 | 0 |

现场报告为 `tmp/field-acceptance/field-20260909T105750Z-12222b15/field-acceptance.json`（SHA-256 `6a301cd28072ebbf01fa07e81d7aaf5c4b2de9741c14ceb351122cac18f21567`），Fixture SHA-256 为 `7573e19271528e904d2eb40cef2765f05d4e5f489f2b35cc1b1359bcd5128759`。Build 14A 正/负资格脚本最新退出码 `0`，覆盖资格拒绝、资格通过、归属隔离、幂等和事务性 Outbox。当前本地现场 Gate **PASSED**；范围仅限本机合成数据，不能外推为生产 SLA、真实用户泛化或真实外部履约接入。

## 2026-09-09 — Docker 恢复后当前提交 Release Gate 通过

当前仓库 HEAD：`84e111d17e4117287660421ea5772a9ddcf44382`。Docker Desktop 已恢复，未修改业务代码、测试预期、Java 契约或数据库结构。主 Compose 以 `docker compose up -d --no-build` 启动，8/8 常驻服务 healthy；`scripts/verify_compose_stack.py` readiness `3/3` 通过。另启动隔离 fault Compose 项目 `mall-field-20260909`，8/8 服务 healthy。

当前现场 Runner 报告：`tmp/field-acceptance/field-20260909T105750Z-12222b15/field-acceptance.json`，SHA-256 `6a301cd28072ebbf01fa07e81d7aaf5c4b2de9741c14ceb351122cac18f21567`；合成 Fixture SHA-256 `7573e19271528e904d2eb40cef2765f05d4e5f489f2b35cc1b1359bcd5128759`。

| 现场类别 | 执行 | 通过 | 失败 | 阻断 |
| --- | ---: | ---: | ---: | ---: |
| browser_e2e | 24 | **24** | 0 | 0 |
| java_mysql_integration | 30 | **30** | 0 | 0 |
| fault_injection | 36 | **36** | 0 | 0 |
| durable_async_recovery | 32 | **32** | 0 | 0 |
| 合计 | **122** | **122** | 0 | 0 |

当前 v3.0 现场 Release Gate：**PASSED**。此前因旧 Fixture 登录阻断的 30 条报告已标记 superseded；不与本轮通过结果相加。该证据只适用于本机 Docker、Chrome、Java/MySQL、Redis/RabbitMQ 和合成数据，不代表生产 SLA、真实用户泛化或真实外部履约接入。

## 2026-09-09 — 当前 CI 安全门禁修复（代码提交 `38601904595b6ae82a1e692d88c33d83d1ba1e01`）

本次更新只修复 `mall2/pom.xml` 的 Netty 安全版本：`4.1.136.Final` → `4.1.137.Final`。此前 `dependency-and-secret-risk` 对 `netty-handler` 报告 `GHSA-c4c3-7fpv-j4q5`（CVSS 9.1）与 `GHSA-fccg-mwvh-qqg4`（CVSS 6.9）；没有关闭扫描或绕过失败。

- `mall-ci` [34333690241](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34333690241)：**success**。
- `quality-evaluation` [34333690290](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34333690290)：**success**。
- 当前提交本机定向 Java 测试：portal **14/14**、admin **6/6**；FastAPI **353/353**；Vue build、Compose config 通过。

这次提交不改变现场验收边界。当前提交尚无新的逐条 browser `24`、Java/MySQL `30`、fault `36`、durable `32` 现场报告；此前 `45f842f` 报告因提交不一致已 stale，且 Docker Desktop 后端 `sailor-ingest.sock` Windows `error 1920` 仍未解除。因此当前 v3.0 Release Gate **未通过**，不能宣传 `122/122` 现场通过。

## 2026-09-09 — v3.0 统一现场 Runner 与当前提交 Release Gate

当前代码提交：`45f842f9ed6c0a9b636e0420fe489312e71a28fb`。本次新增统一入口 `scripts/Verify-FieldAcceptance.ps1` 及四类数据驱动 Runner；新增 Runner 合同测试，未修改业务代码、测试预期、Java 资格或数据库契约。

当前提交的本机确定性结果：FastAPI **353 passed、7 subtests passed**；Runner 合同 **11 passed**；manifest/preflight **478/478、8/8**；Vue build、Compose config、Java portal **14/14**、admin **6/6** 通过。

当前提交现场报告 `tmp/field-acceptance/field-20260909T074151Z-d56eb7fe/field-acceptance.json`（SHA-256 `7da1d8efdd399d354ea535d32f9c24f9405508f5c57f9cb3364223219487e32a`）发现四类 Runner 均为 ready，但 Docker Desktop 后端的 `sailor-ingest.sock` 重命名错误 `error 1920` 阻断了 24 + 30 + 36 + 32 条现场执行，因此当前 Release Gate **未通过**：`0 passed / 122 environment_blocked`。这不是业务测试失败，也不是把未执行写成通过。

2026-09-08 的旧现场报告曾在 Docker/Chrome/Compose 中执行过 browser 24/24、Java/MySQL 30/30、fault 36/36、durable 32/32，但它们绑定 `314f5d9`，与当前代码提交不一致，已在当前证据中标记 **stale**，不与本次报告合并。恢复 Docker 后必须以当前 SHA 重新运行入口；在此之前不能公开写“当前 Commit 的 122 条现场 Case 全部通过”。


## 2026-09-08 — Docker 运行时恢复后的最终现场复验

在最终补测前，Docker Desktop 因 Windows 残留 AF_UNIX/reparse socket 无法启动；已采用可恢复的内部运行时目录改名方案并重新启动，未执行 factory reset、`docker compose down`、卷/VHDX 删除或数据库清空。Docker Engine `29.7.2` 恢复后，Compose 8/8 常驻服务 healthy，`verify_compose_stack.py` 的 Vue/FastAPI/Java readiness `3/3` 通过。

恢复后的合成现场批次：双账号权限、统一售后创建/确认/列表/状态/取消/跨账号、Build 21 同会话重启恢复、MCP 只读隔离、人工协同均 exit `0`；Build 14A 退货状态 exit `1`，原因是当前合成订单被 Java `return_refund` 资格规则拒绝，未放宽断言或伪造通过。完整 `browser_e2e 24`、`java_mysql_integration 30`、`fault_injection 36`、`durable_async_recovery 32` 仍没有逐条独立现场执行器，继续标记 `environment_blocked`，不能由 deterministic `478/478` 代替。

本次结果和命令已同步到 [`v3.0 当前 HEAD 证据`](evidence/v3.0-current-head-evidence.md)；不宣称生产 SLA、真实用户泛化或真实支付/仓储/物流/维修接入。

本次证据同步提交 `73d12c5ecde9c56a21ce7be78e194d8fbc1e837c` 的 GitHub 门禁已完成：[`mall-ci` run 34204868188](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34204868188) 与 [`quality-evaluation` run 34204868215](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34204868215) 均为 `success`。

## 2026-09-08 — 现场验证增量

本次现场补测使用 Docker Compose 的本地合成数据和进程内随机密码。真实 Chrome 页面、统一售后、双账号权限、MCP 只读隔离、人工协同和 Redis/RabbitMQ 重启后的健康恢复均有独立命令证据；Java/MySQL `MallPortalApplicationTests` 在临时本地连接配置下 `1/1` 通过。Build 14A 退货申请因 Java 资格不满足保留失败，Build 21 独立重跑出现一次等待任务缺失，均未转写为通过。

完整 manifest 的 24/30/36/32 条浏览器、Java/MySQL、故障注入和 durable recovery 场景仍未逐条现场执行；它们不能由 deterministic manifest 478/478 代替。项目仍不宣称生产 SLA、真实用户泛化或真实支付/仓储/物流/维修接入。

本次现场证据提交 `dbbd18c029acf8bacc21cada2c161da15185cc42` 已推送并完成远程门禁：[`mall-ci` run 34200061061](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34200061061) 与 [`quality-evaluation` run 34200061063](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34200061063) 均为 `success`。

## 2026-09-08 — 前端展示资产最终现场复验（截图源基线 `3700dde210e9b7737a2181980c50a7885059ead3`）

Docker Desktop 恢复后，使用当前 Compose 服务、真实 Chrome headless/CDP 和合成账号重新生成客户、开放任务 Agent、运营和质量四张截图。八个常驻服务均为 `healthy`，Docker Engine `29.7.2`；没有删除命名卷、演示数据或数据库。该段记录 `4dae57f` 发布提交的资产；2026-09-08 重截后的当前资产哈希见补测证据。

截图/证据提交 `4dae57fc8d0876fb2b343f898489750f8b95c4ab` 已推送并完成远程门禁：[`mall-ci` run 34179749694](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34179749694) 与 [`quality-evaluation` run 34179749709](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34179749709) 均为 `success`。这只覆盖当前工作流门禁，不等价于生产部署、完整浏览器 E2E 或真实模型准确率。

## 2026-09-05 — 当前 HEAD 剩余关键结果补测（代码提交 `38cf3809e48ec08bead6accc07a4ace27ebf5f59`）

当前补测的完整、可审计分层结果见 [`docs/evidence/v3.0-current-head-evidence.md`](evidence/v3.0-current-head-evidence.md) 与同名 JSON。确定性门禁和本机 Compose 健康通过；真实模型开放任务与 Grounding 存在明确质量失败，完整浏览器/Java-MySQL/故障恢复 manifest 尚未逐条现场执行。验证提交 `9fba15ddac537016fca2116286e7238121b1236a` 的 `mall-ci` [33901002046](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/33901002046) 与 `quality-evaluation` [33901002043](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/33901002043) 均为 GitHub 实际 success；历史提交的其他 Actions 链接只代表各自提交。

## 2026-09-04 — 公开演示资产与 CI 复验更新（验证提交 `df67753bb923434c0b5d11e448e778cb413b7840`）

本轮更新了客户页面的泛化输入示例，并从真实本地 Compose 页面重新截取客户、运营和 AI 质量开发者页面。截图只使用合成账号与脱敏/聚合数据，不包含密码、Token、完整订单号、客户原话、RAG 原文或生产 Trace。

本机实际复验结果（不能代替远程 CI）：

- FastAPI 全量：`346 passed`，7 个参数化子断言通过；
- `quality-agent.v2`：`17/17 passed`；`rag-chunk-metadata.v1`：`8/8 passed`；
- v3 manifest/preflight：`478/478` deterministic，代表性 Runtime `8/8`；
- RAG2 Dense、Hybrid、Hybrid+Rerank：各 `52/52 passed`，Dense 继续默认；
- Java portal：`14/14`；Java admin：`6/6`；Vue 生产构建成功；Compose config 成功；八个常驻容器 healthy。

本轮提交已推送并取得与该 SHA 一致的远程门禁结果：`mall-ci` [33868598584](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/33868598584) **success**；`quality-evaluation` [33868598567](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/33868598567) **success**。本机复验和远程 CI 均不等于生产部署、生产 SLA、真实用户准确率或真实外部履约接入。

## 2026-09-04 — Build 22 CI 与 live-synthetic 收口（提交 `f88fee38b2089a0cc433650480ebac6dc3dcba03`）

本次代码提交已推送到 `main`，并取得了**该提交对应**的远程 GitHub Actions 结果：

| 工作流 | 运行 | 结果 | Job 结果 |
| --- | --- | --- | --- |
| `mall-ci` | [33841952626](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/33841952626) | **success** | Python、Java、Web、Compose contract、dependency-and-secret-risk 全部 success |
| `quality-evaluation` | [33841952630](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/33841952630) | **success** | isolated-quality-evaluation success |

本次提交的实际改动和本机复核如下：

- CI 质量工作流纳入 live-synthetic runner 合同测试；`call_skill` 的 Prompt 明确只允许只读 Skill，写能力只能生成 ActionProposal 并等待确认。
- MongoDB Driver 固定为 `4.11.5`，新增 Micrometer Mongo API 兼容回归测试，避免健康检查在运行时出现 `NoSuchMethodError`。
- Build 21 现场验收脚本对齐 v3 `task`/`waiting_input` 语义，不再把缺订单号写成旧式 pending action 或默认 interrupt。
- 36 条人工 live-synthetic Case 各运行 3 次：**108/108 passed**，本机 p95 约 **1438 ms**；仅使用版本化合成消息和真实 P0 模型，不访问生产会话或业务写接口。
- FastAPI 全量：**346 passed，7 subtests passed**；v3 manifest **478/478**，代表性 Runtime **8/8**；质量 Agent **17/17**；任务编排 contract_mock **11/11**；RAG 合同 **55/55**；Chunk/Metadata **8/8**。
- Java portal 定向 **14/14**、admin 定向 **6/6**；Vue 生产构建和 Compose 静态合同通过。

本机没有安装 gitleaks/OSV 命令行二进制，因此安全扫描的最终依据是上表中 GitHub runner 的真实 job；该 job 成功不表示 Java 8/Spring Boot 2.7 的时间限定 OSV 例外已经消失。浏览器 E2E manifest 的 24 条和 Java/MySQL manifest 的 30 条仍是合成合同清单，未被本次记录冒充为逐条现场运行。

## 2026-09-03 — GitHub Actions 远程门禁验证（代码验证基线 `d7c8f9bf4354f05009b9f83c793a3f296619bf66`）

代码验证基线及其后续仅文档同步提交的远程运行均已实际完成，不能用本机结果替代：

| 工作流 | 运行 | 结果 | Job 结果 |
| --- | --- | --- | --- |
| `mall-ci` | [33746095478](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/33746095478) | **success** | Python、Java、Web、Compose contract、dependency-and-secret-risk 全部 success |
| `quality-evaluation` | [33746095446](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/33746095446) | **success** | isolated-quality-evaluation success |

工作流执行的门禁命令已提交在 [.github/workflows/ci.yml](../.github/workflows/ci.yml) 和 [.github/workflows/quality-evaluation.yml](../.github/workflows/quality-evaluation.yml)。本机等价复核记录为：FastAPI `343 passed`、`7 subtests passed`；Java portal 定向 `13/13`、admin 定向 `6/6`；Vue `npm run build` 成功；OSV v2 直接清单扫描 **无未处理结果**。Java 8/Spring Boot 2.7 的无法在当前兼容线修复的风险仍以有期限例外保留在 `osv-scanner.toml`，不应解读为漏洞清零。这些是分项证据，不能相加，也不代表生产 SLA 或真实用户准确率。

## 2026-09-03 — Mall v3.0 Runtime 发布硬化（本地证据）

本次在既有 v3 Runtime 基础上补齐了可追溯的 release manifest、确定性发布预检、CI 接线和公开证据入口。`evals/v3/release-manifest.json` 当前包含 **478 条唯一 deterministic Case、36 条手工 live-synthetic Case、12 个性能 Profile**；其分类数量、fixture hash、预算、可执行断言和禁止跳过字段由 `mall-ai-service/scripts/validate_v3_release_manifest.py` 校验。

截至本记录生成时，本机预检实际结果为：**478/478 注册 Case、8/8 代表性 Task Runtime 安全冒烟通过**，无模型 Key、无 Java/数据库/业务写入。新增的 `tests/test_release_manifest.py` 与 `tests/test_release_evaluation.py` 也纳入 FastAPI 全量回归。该结果是本机 deterministic/合成证据；远程门禁结果另见上方真实 Actions 运行记录。

发布集成方式为单一根仓库快照：不提交 `mall2/.git`，保留根目录及 `mall2/LICENSE`、NOTICE、上游归属，并在 [UPSTREAM.md](../UPSTREAM.md) 说明 `macrozheng/mall` 二次开发边界。未提交 `.env`、密码、Token、模型权重、Chroma 索引、客户数据或完整 Trace。

历史发布准备记录更新时间：2026-09-01。本文记录本仓库公开发布准备阶段实际完成的工作，严格区分已验证事实、已知边界和待补材料。账号密码、API Key、Token、真实订单、真实客户对话、Docker 卷和本地模型/索引均不在仓库或本文中。

## 发布范围

- 公开仓库：`Eleven617/mall-ai-after-sales-platform`。
- 发布内容：可复现的本地合成演示代码、文档、测试与启动脚本。
- 不包含：真实生产数据、密钥、预构建的 Chroma 索引、本地 Embedding/Reranker 权重、Docker 命名卷、日志或浏览器会话数据。
- 视频演示：有意留待后续制作；当前仓库已经提供文字演示脚本，不将“视频已完成”作为发布结论。

## 本次公开发布复核

以下是为公开发布额外执行的最小可复现验证。它与 [测试与演示证据](TEST_AND_DEMO_EVIDENCE.md) 中较早的、范围更广的产品验收快照不是同一条命令记录；测试选择和数量不能相加，也不应据此推导生产质量。

| 范围 | 实际结果 |
| --- | --- |
| Git 发布 | 发布前发现旧父提交含静态 Postman 认证值，因此以相同的当前脱敏内容建立无旧父历史的干净发布提交；随后重新克隆远端核对。 |
| FastAPI | 全量回归：`291 passed`、`20 subtests passed`。 |
| Vue | 类型检查和生产构建通过；依赖审计结果为 `0 vulnerabilities`。 |
| Java 定向测试 | portal 定向测试 `12 passed`；admin 定向测试 `6 passed`。 |
| Compose 合同 | `docker compose config --quiet` 通过。 |
| 可复现 RAG 准备 | 从干净克隆构建 AI 服务镜像成功；首次本地准备成功下载公开 BGE 模型并构建 `15` 条政策 chunk。 |
| Docker 本机验收 | 未执行 `docker compose down` 或卷删除；八个常驻服务均健康，网站与 FastAPI readiness 均返回 HTTP 200。 |

上述结果只说明当前机器、当前合成数据和当前依赖版本下的验证范围；不等价于生产部署、生产 SLA、真实模型泛化准确率或第三方履约系统接入。

## 已知边界与未验证项

1. Java 全量 Maven 测试未作为本次“全部通过”结论。历史 `MallPortalApplicationTests` 需要可达的 MySQL 集成环境，在本机曾因 `Public Key Retrieval is not allowed` 失败；这不是已通过的业务单测，故只报告上述显式定向测试结果。
2. 本次提交对应的 `mall-ci` 与 `quality-evaluation` 已取得远端成功运行记录（见本文顶部链接）。这只证明该提交在 GitHub runner 上通过了当前门禁，不等于生产部署、生产 SLA 或真实模型泛化能力。
3. 本地 Docker 验收保留已有命名卷和合成演示数据；没有清库、删卷、删历史日志或模拟外部支付/仓储/物流/维修成功。
4. 真实模型调用需要由使用者在本机配置自己的密钥和可达网络；无模型配置时系统会安全停止模型相关请求，仍可做结构与权限验证。
5. 清理后的 `main` 不再包含旧认证值的可达提交；已经获取过旧提交的本地克隆、缓存或镜像不受 Git 历史重写控制。若该旧值曾在某个真实环境中有效，应由该环境维护者单独轮换对应的认证签名/会话密钥。

## 复现入口

从干净克隆启动、设置本机演示身份和运行验证命令见根目录 [README](../README.md) 与 [测试与演示证据](TEST_AND_DEMO_EVIDENCE.md)。公开前仍应按 [公开前检查清单](PUBLIC_RELEASE_CHECKLIST.md) 完成维护者自己的许可证和敏感信息复核。
