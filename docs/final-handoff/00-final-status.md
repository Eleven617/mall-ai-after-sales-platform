# Mall v3.0 最终交付状态

## 当前权威快照｜v3.0.4 在线入口预检修复（2026-09-19）

候选 Runtime `3c4c3a5ae9fac944350b6710322fd9d5223eccde` 已将 `MALL_LIVE_DEMO_PASSWORD` 的宿主 Runner、PowerShell 与 Compose 路径统一，并在生成在线 Batch、Release Lock、报告或账本事件前执行本地 Java 合成账号预检。预检缺失或无效时 fail-closed，且不创建在线批次工件、不调用 Provider。

本机未配置该 Secret，故本阶段为 **`BLOCKED_MISSING_LIVE_DEMO_PASSWORD`**：Provider requests=0、Token=0。历史失败 Lock/Report/Ledger 保持原样；当前 Runtime 的现场 122 条尚未重新执行，旧 122/122 不能并入。FastAPI 机器报告为 449/449（437 pytest cases + 12 subtests），Release 仍为 **`NOT_COMPLETE`**。

## 当前权威快照｜v3.0.4 离线候选（2026-09-18）

分支 `codex/v3.0.4-eval-contract-alignment`，Runtime Freeze `267e3b70e73cedb4ff714857a2195d56d4799161`。FastAPI JUnit **444/444**（432 pytest cases + 12 subtests），manifest 478/478、代表性 8/8、Java 定向测试、Vue build 与 Compose 配置均通过。

Docker 主栈 8/8 healthy，AI Runtime image revision 与 Freeze 一致。当前合成现场 Runner 从零通过 **122/122**：Browser 24/24、Java/MySQL 30/30、Fault 36/36、Durable 32/32；failed=0、environmentBlocked=0。报告 SHA-256 `4db9cca31a2ab77af02f2ddf9892a933ab75821c431df268ae10e89ecad8b2a9`，Fixture SHA-256 `7573e19271528e904d2eb40cef2765f05d4e5f489f2b35cc1b1359bcd5128759`。

发布门禁 **`NOT_COMPLETE`**：本轮 DeepSeek `not_run_by_design`，calls=0、Token=0；没有创建 Release/Lock、没有修改 README 或合并 main。当前 SHA 的 CI 为 `pending_remote_final_sha`，仅等待一次独立正式在线批次授权。历史失败批次及其账本/锁保持不变。

## 当前权威快照｜v3.0.2 唯一正式 DeepSeek 批次（2026-09-16）

v3.0.2 候选分支 `codex/v3.0.2-offline-candidate`（HEAD `a9271ac295d98d265ffdd54b03333734b1beea4c`），运行时冻结 `061d60bb13004dc7df57a161b01e378335f8938c`。唯一正式批次 `candidate-61f2a1fd5453` **FAILED**，Release Gate **未通过**，`V3_0_2_LIVE_READY=false`（在线结论）。第一展示链在 `java_commit` 阶段因 `commit_skill_not_allowlisted` fail-closed；没有 Java 写入。报告、Lock 与 Ledger 的 SHA-256 见 `docs/evidence/release-gate-summary.md`；不重跑、不创建第二批次、不更新 README、不合并 main。离线候选门禁仍为通过，但不能替代在线模型验收。

## 当前权威快照｜v3.0.2 离线候选（2026-09-15）

冻结 SHA `061d60bb13004dc7df57a161b01e378335f8938c`，分支 `codex/v3.0.2-offline-candidate`。`V3_0_2_LIVE_READY` 已通过，且证据提交 `dc7dee733ed056af054450df9b1399e199812539` 的 [`mall-ci`](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34978867905) 与 [`quality-evaluation`](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34978867657) 均成功；发布状态仍 **NOT_COMPLETE**，因为在线模型批次尚未授权。

- FastAPI：399 passed、0 failed、0 skipped；Java portal/admin/Spring：14/14、6/6、1/1；Vue build passed。
- deterministic manifest/preflight：478/478、代表性 8/8；RAG 合同：21/21。
- 冻结 SHA 本机合成现场：browser 24/24、Java/MySQL 30/30、fault 36/36、durable 32/32，合计 122/122，0 failed、0 environment_blocked。
- 公共 Nginx 慢调用：76.125 秒、HTTP 201、`ready_to_commit`；Provider 请求 0、Java 最终写入 0，Runtime 在 240 秒上限内。
- 本轮 DeepSeek 调用 0。v3.0.1 的失败根因固定为 `gateway_timeout_before_agent_completion`，旧报告/ledger/lock 未修改。

上述证据均为本地合成/确定性范围，不能扩大为生产 SLA、真实用户泛化或外部履约成功。

## 当前权威快照｜v3.0.1 在线验收（2026-09-15）

运行时代码 `06ef600e51e7b0dc362d43a98e274c28144738d8`，分支 `codex/v3.0.1-offline-acceptance`。离线 readiness 24/24 通过；FastAPI 382 passed、v3 deterministic 478/478、Vue build、Java portal 14/14 + Spring 1/1、当前本机合成现场 122/122 通过。唯一正式 DeepSeek candidate 在第一条展示链失败，锁状态 `FAILED`，因此 **Release Gate：NOT_COMPLETE**。

正式批次报告 `tmp/deepseek-v3.0.1-final-06ef600e51e7b0dc362d43a98e274c28144738d8.json`（SHA-256 `6615d069122cb66ee8f3467f98ae79457ef287afd6f19c5e56035c45fb0b65c8`）；共享账本观察 9 次 Provider 请求、9 成功、0 失败、27,329 tokens。main/supplemental/Grounding 未执行；该计数不等于任务准确率。现场报告 `tmp/offline-field-acceptance/field-20260915T064300Z-99f3dc2f/field-acceptance.json`（SHA-256 `ec337708baa422fcd11bf2ac2334372e88f3592f4dde454ab0f674413704122b`）。

本轮不生成 live GIF、不宣称真实模型泛化、生产 SLA、真实支付/仓储/物流/维修或完整 CI 通过；提交 `5629f7b` 已推送，[`quality-evaluation`](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34941472352) 成功，[`mall-ci`](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34941472321) 在 `public-release` 因公开验证器仍要求历史 FastAPI 381 而失败。候选锁定后不修改验证器、不重跑模型。

## 当前权威快照｜v3.0.1 候选验收（2026-09-14 UTC）

运行时代码：`54de463b4990229b591e1fd0a278f754bf240678`；分支：`codex/v3.0.1-offline-acceptance`。当前公开展示 Release Gate：**NOT_COMPLETE**。FastAPI **381**、12 个子断言；v3 deterministic 478/478、代表性 8/8；浏览器 24/24、Java/MySQL 30/30、故障注入 36/36、Durable 32/32，`environment_blocked=0`。本轮 DeepSeek `not_run_by_design`；deterministic/replay 展示链通过，但不等于真实模型泛化。

旧的 72/72、36/36、Grounding 和 122/122 Durable 报告绑定旧 Runtime，不能替代当前结果。提交 `5bfdc3c` 的 `mall-ci` 与 `quality-evaluation` 已实际 success；这证明 GitHub runner 门禁通过，不代表生产 SLA、真实用户泛化、真实外部支付/仓储/物流/维修履约或模型成本。唯一事实源：[`current-release-facts.json`](../evidence/current-release-facts.json)。

本轮包含代码与证据的提交 `bd3a5cf` 远程门禁也已通过：[`mall-ci`](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34931831197)、[`quality-evaluation`](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34931831222)。

## 历史审计记录（以下内容不代表当前 Commit）

## 2026-09-12｜当前代码最终快照

本节覆盖运行时代码提交 `52d5482455e2389cfd6c2ef15d233712607ffa9f`。此前日期段落是历史交接记录；若提交或报告不一致，以本节和 `docs/evidence/final-agent-quality-baseline.md` 为准。

- FastAPI：362 passed；Java portal/admin：12/12、6/6；Spring context：1/1；Vue build：passed。
- Live synthetic：main 72/72、holdout 36/36；Grounding 15/15、57/57 checks；v3 deterministic 478/478、代表性 8/8。
- 本地现场 Runner：browser 24/24、Java/MySQL 30/30、fault 36/36、durable 32/32，合计 122/122，0 failed，0 environment_blocked。
- 现场报告：`tmp/field-acceptance-final/field-20260911T203212Z-95f5755e/field-acceptance.json`，SHA-256 `a0fbcd5c22638be8be480ae08344596a14d7874eafcd65194242b3f4df8c803e`；Fixture SHA-256 `d4829bd272dad498b17890b24595c288150ed89d4f59b062424b70067513e093`。

当前本机合成 Gate 通过；证据提交 `efd3dcdd5d9c628a98b697ad63b57fe78b932cd9` 的远程 Actions 也已通过：[`mall-ci` run 34646346032](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34646346032)、[`quality-evaluation` run 34646346115](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34646346115)。以上不代表生产部署、生产 SLA、真实用户泛化或真实支付/仓储/物流/维修接入。

## 当前结论

**CLOSED**

本地代码、Docker 现场、Build 14A 正/负路径和证据包均已完成。交接包基线提交 `cfbe952375dcd50cbbc1f96edf82a1a2261d7aa4` 的 `mall-ci` 与 `quality-evaluation` 已在 GitHub 实际 success；本次状态文字提交只增加收尾文档，不改变被测运行时代码。

- [`mall-ci` run 34347831789](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34347831789)
- [`quality-evaluation` run 34347831778](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34347831778)

这里的 CLOSED 只表示本次约定的本地合成数据发布门禁已完成；它不表示生产上线、真实用户泛化、真实外部支付/仓储/物流/维修接入或生产 SLA。

## Git 与证据绑定

| 项目 | 值 |
| --- | --- |
| 仓库 | `Eleven617/mall-ai-after-sales-platform` |
| 分支 | `main` |
| 运行时代码提交 | `84e111d17e4117287660421ea5772a9ddcf44382` |
| 证据同步基线 | `5ea119970a2a4a9a9194dc3e1e46eff412bd406e` |
| 说明 | `5ea1199` 及本交接提交只增加证据/交接文档，不改变被测业务代码 |
| 工作区（复核开始） | clean |
| 远程 | `https://github.com/Eleven617/mall-ai-after-sales-platform.git` |

## 核心交付门禁

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| Docker/Compose | passed | Engine `29.7.2`；主 Compose 8/8 healthy；readiness 3/3 |
| 四类现场 Runner | passed | `field-20260909T105750Z-12222b15`，122/122，0 failed，0 blocked |
| Build 14A | passed | 负资格拒绝 + 正资格通过 + 归属隔离 + 幂等 + Outbox，脚本 exit 0 |
| FastAPI 回归 | passed | 353 passed，7 个子断言，1 条第三方弃用警告 |
| Java 定向测试 | passed | portal 14/14，admin 6/6，均显式 `-DskipTests=false` |
| Vue 构建 | passed | `npm run build` exit 0 |
| v3 deterministic gate | passed | manifest 478/478，preflight 8/8 |
| 远程 CI | passed（以当前文档提交最终复核） | `mall-ci` 与 `quality-evaluation` 均需与最终提交 SHA 对齐 |

## 现场 Runner 分项

| 类别 | 执行 | 通过 | 失败 | environment_blocked | 模式 |
| --- | ---: | ---: | ---: | ---: | --- |
| browser_e2e | 24 | 24 | 0 | 0 | live_browser |
| java_mysql_integration | 30 | 30 | 0 | 0 | live_java_mysql |
| fault_injection | 36 | 36 | 0 | 0 | isolated_compose_fault / runtime contract |
| durable_async_recovery | 32 | 32 | 0 | 0 | live_build21_restart_recovery |
| 合计 | **122** | **122** | **0** | **0** | 本机 Docker 与合成 Fixture |

现场报告：`tmp/field-acceptance/field-20260909T105750Z-12222b15/field-acceptance.json`。

- 报告 SHA-256：`6a301cd28072ebbf01fa07e81d7aaf5c4b2de9741c14ceb351122cac18f21567`
- Fixture SHA-256：`7573e19271528e904d2eb40cef2765f05d4e5f489f2b35cc1b1359bcd5128759`
- `testedCodeCommit`：`84e111d17e4117287660421ea5772a9ddcf44382`
- 运行时长：211947 ms

旧 Fixture 造成的 122 条阻断报告和更早提交的现场结果全部保留为 superseded/stale，不与本次结果相加。

## 仍然不能宣称

- 不是生产 SaaS、生产 SLA、真实吞吐或真实用户准确率。
- 没有接入真实支付、仓储、物流、维修系统；履约未配置时保持人工/未开始状态。
- live-model synthetic 结果是小规模合成评测，不能等同于自然语言泛化能力。
- 个人贡献边界不能从提交历史自动推断；上游 `macrozheng/mall` 能力不归为个人原创。
