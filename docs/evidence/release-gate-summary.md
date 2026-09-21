# Mall v3.0 Release Gate 复核

## 当前权威快照｜v3.0.4 离线收口候选（2026-09-21）

Release Gate：**NOT_COMPLETE**。当前 Runtime/image `8ff255aeff320b5f3800aa05bfacefec975a684a` 的 FastAPI JUnit **483/483**（467 cases + 16 subtests）、manifest **478/478**、representative **8/8**、contract replay **36/36** 均通过。主 Compose **8/8 healthy**；同一冻结版本从 0/122 完整现场通过 Browser 24、Java/MySQL 30、隔离 Compose Fault 36、Durable Recovery 32，failed 0、environmentBlocked 0。

现场报告 `tmp/v304-field-acceptance-8ff255a-corrected/field-20260921T114110Z-54e374ab/field-acceptance.json`，SHA-256 `7156497d23080a7aac6a7d4183949b7d11c41ec8c9ae8799e53722773b26a64c`；Fixture SHA-256 `7b7616e3ba0f6939a7bcc7d381b3c3b7b35d2b443c2056b218cdefc7f17486a9`。确定性展示链 3/3、12 帧，报告 SHA-256 `07638edf7377bec1d510fd4580874231bf6342b7cbeef84b4253f1db8187e1d0`；关键状态卡跨场景不重复。本轮外部 Provider requests/tokens 均为 0，未创建在线 Release/Batch/Lock，未合并 `main`。

历史在线最小复测仍是 FAILED：21 次 HTTP attempts、19 成功、2 次 network 失败、73,833 tokens，11 个目标/对照未执行。当前候选只具备一次最小在线复测的工程入口，不得把 deterministic 素材或 122/122 写成真实模型效果。

## 历史快照｜v3.0.4 最小在线复测取证与离线修复（2026-09-21）

Release Gate：**NOT_COMPLETE**。Release `mall-v3.0.4-minimal-retest-78c7dd5-20260921` / Batch `minimal_retest-d551e9d01402` 已真实运行：Provider 逻辑请求/HTTP attempts `21/21`，成功 `19`、网络失败 `2`、Token `73,833`，Ledger 完整对账。三条展示链业务断言 `3/3` 通过，但 11 个目标/对照评测均 `not_executed`，素材存在跨场景重复帧，不能发布。

离线修复 Runtime `e1df8c4266f676330cb4c581a0c105dab10932a7` 的 FastAPI JUnit **477/477**（461 cases + 16 subtests）、manifest **478/478**、representative **8/8**、contract replay **36/36**。旧现场 **122/122** 只绑定 Runtime/image `78c7dd5`，不冒充当前 Runtime 验证。本轮新增外部 Provider 请求为 0；历史 Report/Ledger/Lock 未修改。

## 历史候选｜v3.0.4 最小在线复测前冻结（2026-09-21）

候选分支 `codex/v3.0.4-eval-contract-alignment`，Runtime `78c7dd5c0156d7d4b18df75b0df6221b6b2b4df4`。FastAPI JUnit **473/473**（457 pytest cases + 16 subtests），manifest **478/478**、representative **8/8**、contract replay **36/36**，三套 Agent Suite 语义审计均为 0。当前镜像现场从零通过 **122/122**：Browser 24、Java/MySQL 30、Fault 36、Durable 32；报告 SHA-256 `b03b6cee49951b301e13dc38531834cb65e210df0d351f6d659c74bd55cf18ec`，Fixture SHA-256 `7b7616e3ba0f6939a7bcc7d381b3c3b7b35d2b443c2056b218cdefc7f17486a9`。本轮 Provider requests/tokens 均为 0；当前 SHA 的远程 CI 尚未执行，最小在线复测 `not_run_by_design`，Release Gate **NOT_COMPLETE**。旧在线 Report/Ledger/Lock 保持不变。

## 当前权威结论｜v3.0.4 在线入口 Ledger 缺陷校准（2026-09-20）

已确认失败根因为正式入口只创建 Ledger 目录、没有原子创建空 `ledger.jsonl`；`reserve_provider_attempt()` 因 Ledger 缺失在网络前 fail-closed。该批次应标记为 `invalidated_before_provider_network` / `release_infrastructure_failure`：`providerHttpAttempts=0`、成功请求 0、Token 0。报告中的 `task_terminal_state_unexpected` 仅是 Runner 表象，不是模型质量或 Agent 业务失败。旧 Report/Ledger/Lock 未修改；本轮没有新的外部 Provider 请求。

入口已改为在创建 Batch/Lock 前原子创建全新的空 JSONL，并拒绝复用已有 Ledger/Lock 或错误容器路径；`release_ledger.py` 的缺失文件 fail-closed 行为保留。Fake Provider 演练证明首次 reservation/settlement 可对账（HTTP attempts 1、Provider requests 1、Token 5），不触发 DeepSeek。

## 当前权威结论｜v3.0.4 唯一正式在线批次（2026-09-20）

Runtime Freeze `3c4c3a5ae9fac944350b6710322fd9d5223eccde` 的唯一正式 Release `mall-v3.0.4-portfolio-final-3c4c3a5a` 已执行。无模型预检先通过两条本地 Java 合成账号创建/登录；随后 Batch `portfolio_final-3d7b9340d60d` 在首条展示链 `main_open_task_closed_loop` 的 `agent_task_create` 阶段停止，安全失败码 `task_terminal_state_unexpected`。状态转换为 `task_created -> task_blocked`，Proposal 未形成，工具调用 0，Java 资格核验/最终写入/状态回查均为 0。

共享 Ledger 对账：Provider 逻辑请求 1、失败 1、Token 0、HTTP attempts 0；不是网关、Docker 或 Java 环境错误。批次报告 SHA-256 `d3508d1f485e77944ad3db62dfe7fc8298b83746ce9ad1bec86d23b5e8f1521c`，Ledger SHA-256 `cd3ea9cb26a1e32764e8888f26302a8e4eaac16d587197ff06cec925c71fe10b`，不可变 Lock SHA-256 `d9b65d14c1ae4c8b8be135b4a1d4bdb96cdde764e2f0988721714462ed91313c`。主集、补充集、Grounding、另外两条展示链和最终在线素材均未执行；本轮不重试、不创建第二批次。

**Release Gate：`NOT_COMPLETE`。** 当前离线工程验证仍有效（FastAPI 455/455、现场 122/122），但该在线核心链失败，不能合并 `main` 或宣称真实模型质量/作品集发布完成。

## 当前权威结论｜v3.0.4 离线现场复核（2026-09-20）

候选分支 `codex/v3.0.4-eval-contract-alignment` 的执行 HEAD 为 `1efaa22311e41d92816c5f08188a59ff7ca66806`；运行时冻结与镜像 revision 为 `3c4c3a5ae9fac944350b6710322fd9d5223eccde`。Docker Desktop/Compose 主栈 8/8 healthy，现场 Runner 使用仓库内 deterministic Fake Provider，从 0/122 完整执行并通过：Browser 24/24、Java/MySQL 30/30、Fault 36/36、Durable Recovery 32/32。

报告：`tmp/v304-field-acceptance-122/field-20260920T053042Z-14d730d7/field-acceptance.json`；Report SHA-256 `3aa1613e07ae89fbf11ad51cd6ed33e0860304040c49abb7a5c03b35adfefe1f`；Fixture SHA-256 `7b7616e3ba0f6939a7bcc7d381b3c3b7b35d2b443c2056b218cdefc7f17486a9`。本轮 externalProviderRequests=0、externalProviderTokens=0；主栈已恢复 offline 模式，独立 fault Compose 项目已按项目名清理且未删除卷。

**Release Gate：`NOT_COMPLETE`。** 离线工程验证已完成，但本轮没有启动 DeepSeek 正式在线批次、没有创建新 Release/Lock、没有合并 `main`；122/122 不能表述为真实模型效果或生产能力。历史失败 Lock/Ledger/报告保持原样。

## 当前权威结论｜v3.0.4 在线入口预检修复（2026-09-19）

Runtime 候选 `3c4c3a5ae9fac944350b6710322fd9d5223eccde` 在创建任何新 Release、Batch、Ledger、Lock 或报告之前，新增了 fail-closed 的 `MALL_LIVE_DEMO_PASSWORD` 检查与本地 Java 合成账号登录预检。宿主 Python Runner、PowerShell 入口与 Compose 容器均使用同一变量名；密码值不会进入 Git、报告、账本、Trace、日志或错误文本。

本次入口收口已支持进程内生成随机临时合成密码，并通过 Java 账号预检；密码不会写入仓库、报告、Ledger、Trace 或日志。当前 Docker CLI/Java 现场在本机执行环境被拒绝访问，故没有启动在线批次。Provider 请求 **0**、Token **0**；旧 `mall-v3.0.4-portfolio-final-267e3b70` FAILED Lock、报告与空 Ledger 均未改写。新的 FastAPI 机器报告为 **450/450**（438 pytest cases + 12 subtests）；预检契约测试通过 **19/19**。此前 Runtime 的 122/122 为历史 deterministic/offline 现场结果，因 Runtime 变更不可并入当前候选。

要继续，需在具备 Docker Desktop、Java 和本地 Compose 权限的 Windows PowerShell 中运行正式入口；入口会在进程内生成临时密码并先做无模型 Java 预检。预检失败不创建 Release/Lock，也不调用 Provider；本阶段 Release Gate 仍为 **`NOT_COMPLETE`**。

## 当前权威结论｜v3.0.4 离线候选（2026-09-18）

候选分支 `codex/v3.0.4-eval-contract-alignment`，Runtime Freeze `267e3b70e73cedb4ff714857a2195d56d4799161`。FastAPI 为 **444/444**（432 pytest cases + 12 subtests，0 failed、0 skipped）；manifest **478/478**、代表性 **8/8**；Java portal/admin、Vue build 和 Compose 配置均通过。

当前一次性现场报告从 `0/122` 执行并通过：Browser **24/24**、Java/MySQL **30/30**、Fault **36/36**、Durable Recovery **32/32**，failed **0**、environmentBlocked **0**。报告 `tmp/v304-field-acceptance-v267-livefault/field-20260918T113619Z-83fcab68/field-acceptance.json`，SHA-256 `4db9cca31a2ab77af02f2ddf9892a933ab75821c431df268ae10e89ecad8b2a9`；合成 Fixture SHA-256 `7573e19271528e904d2eb40cef2765f05d4e5f489f2b35cc1b1359bcd5128759`。Docker 主栈 8/8 healthy，AI Runtime image revision 与 Freeze 一致。

**Release Gate：`NOT_COMPLETE`。** 本轮 DeepSeek 为 `not_run_by_design`，calls **0**、Token **0**；未创建 Release/Lock、未修改 README、未合并 `main`。下一步仅是单独授权的一次正式在线批次。旧失败 Release、Ledger 与 Lock 均保留为历史证据，不计入当前离线结果；当前 SHA 的远程 CI 状态为 `pending_remote_final_sha`。

## 当前权威结论｜v3.0.2 唯一正式 DeepSeek 批次（2026-09-16）

运行时冻结 `061d60bb13004dc7df57a161b01e378335f8938c`，候选分支 `codex/v3.0.2-offline-candidate`，候选 HEAD `a9271ac295d98d265ffdd54b03333734b1beea4c`。Docker Engine `29.8.0` 已恢复，Compose 八个服务均为 `healthy`，运行时身份与冻结 SHA 一致。

唯一正式批次 Release ID 为 `v3.0.2-final-061d60bb13004dc7df57a161b01e378335f8938c`，Batch ID `candidate-61f2a1fd5453`。批次 **FAILED，Release Gate 未通过，V3_0_2_LIVE_READY=false（在线验收结论）**；不重跑、不创建第二批次。第一条 `main_open_task_closed_loop` 在 `java_commit` 阶段停止，安全失败码为 `closed_loop_java_submission_missing`，网关记录 `commit_skill_not_allowlisted`；Proposal 已形成但没有 Java 最终写入。浏览器帧、暂停恢复链、事实变化链、主评测集、补充评测集和 Grounding 均未执行。

| 项目 | 结果 |
| --- | --- |
| Provider | 9 请求、9 成功、0 失败；总 Token 27661（仅本批次账本元数据） |
| 共享在线 Ledger | 对账通过；`tmp/release-ledger-v3.0.2-online/ledger.jsonl` SHA-256 `583193cf2538494c3368d524ffa5c482e88d56daa7d2210166b8aec396ec0731` |
| 批次报告 | `tmp/deepseek-v3.0.2-final-061d60bb13004dc7df57a161b01e378335f8938c.json`，SHA-256 `9bb76cab99e6bd3b761fc57d0ba76411bb0f373cefe5fe15ce384efb6a98ee1f` |
| Release Lock | `docs/evidence/deepseek-release-lock-v3.0.2-final-061d60bb13004dc7df57a161b01e378335f8938c.json`，状态 `FAILED`，SHA-256 `ca5a027e554a4f76a435bbebfc166c0c1d386b9bc41871adbf0568e3b4dba531` |
| 离线候选 | `OFFLINE_ACCEPTANCE_COMPLETE=true` 等离线条件仍成立；不等同于在线模型发布资格 |
| GitHub Actions / main | 本批次失败，未推送新代码、未更新 README、未 fast-forward main；没有可填写的新 Actions 链接 |

本节只记录当前正式批次；v3.0.1 历史 Lock、Ledger 和报告保持原样。失败不是 Provider 超时或模型 HTTP 失败，而是受控 Skill 合同不匹配；不得把 9 次成功请求解释为任务准确率、泛化率或生产能力。

## 当前权威结论｜v3.0.2 离线候选（2026-09-15）

冻结运行时代码 `061d60bb13004dc7df57a161b01e378335f8938c`，分支 `codex/v3.0.2-offline-candidate`。离线候选门禁 **NOT_COMPLETE（等待远程 CI 与单独在线授权）**，但本机离线验收条件已满足：`OFFLINE_ACCEPTANCE_COMPLETE=true`、慢网关、ledger 对账、动态公共校验均通过，外部 Provider 请求为 `0`。

| 门禁 | 结果 | 证据/口径 |
| --- | --- | --- |
| FastAPI | **399 passed / 0 failed / 0 skipped** | `run_fastapi_ci_report.py`，JUnit/sidecar 动态报告，exit `0` |
| Java / Web | portal **14/14**、admin **6/6**、Spring **1/1**；Vue build passed | Maven 显式 `-DskipTests=false`；`npm run build` |
| Manifest / RAG | **478/478；代表性 8/8**；RAG 合同 **21/21** | deterministic/contract_mock，无外部模型 |
| 现场 Runner | **122/122** | browser 24、Java/MySQL 30、fault 36、durable 32；当前冻结 SHA、合成 Fixture |
| 慢网关现场 | **76.125 秒，HTTP 201，ready_to_commit** | 公共 Nginx `/api/agent-tasks`；Provider 0；Java 写入 0；Runtime < 240 秒 |
| 展示链 | deterministic **3/3**；replay **3/3**，各 12 帧 | Provider 0；不等于真实模型泛化 |
| 在线 DeepSeek | **not_run_by_design** | 本轮明确禁止外部模型；v3.0.1 失败批次原样保留 |

现场报告：`tmp/offline-field-acceptance/field-20260915T133506Z-6b5f7e64/field-acceptance.json`，SHA-256 `fbf3e333ea09cc6010e6d1b67fdb82cb762cdb707a9561fb6478655291d00d84`，Fixture SHA-256 `ba77efdd1b2112d2a2dc50561cb3d7fcd041a48d07a00e7bf7611fac103cab6d`。慢调用报告 SHA-256 `7415253e3ee4b82c41ec2e00f7296d58f9f1e5160243b1d0ae59321e674e7652`；ledger SHA-256 `ce801099cd16a998bf39dae544425acb1fd5c6a6c353a1ce18035a1cb8a92323`。v3.0.1 的失败锁与报告未修改。

当前分支的远程门禁已真实通过：[`mall-ci`](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34978867905)、[`quality-evaluation`](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34978867657)，对应提交 `dc7dee733ed056af054450df9b1399e199812539`。这不改变离线候选的边界：不能宣称生产 SLA、真实用户泛化、真实支付/仓储/物流/维修履约或在线模型效果；`environment_blocked=0` 仅适用于本次本机现场 Runner。

## 当前权威结论｜v3.0.1 在线验收（2026-09-15）

代码冻结 `06ef600e51e7b0dc362d43a98e274c28144738d8`；离线 readiness 24/24 通过；FastAPI 382、deterministic 478/478、Java 14/14 + Spring 1/1、Vue build、当前本机合成现场 122/122 通过。唯一 DeepSeek candidate 在第一展示链失败，锁定 `FAILED`，Release Gate **NOT_COMPLETE**。共享 ledger 观察 9 次 Provider 请求、9 成功、0 失败、27,329 tokens；main/supplemental/Grounding 未执行。提交 `5629f7b3529ef03b6833b329b580f212c96b38bb` 的 quality-evaluation [run 34941472352](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34941472352) 成功，mall-ci [run 34941472321](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34941472321) 失败于 `public-release` 的旧 381 断言。

正式候选报告 SHA-256 `6615d069122cb66ee8f3467f98ae79457ef287afd6f19c5e56035c45fb0b65c8`；现场报告 SHA-256 `ec337708baa422fcd11bf2ac2334372e88f3592f4dde454ab0f674413704122b`。本轮 GitHub push 因 443 超时，当前 SHA 的 Actions 尚未验证；旧 run 不替代。

## 当前权威结论｜最终公开收口

运行时代码 `54de463b4990229b591e1fd0a278f754bf240678`，分支 `codex/v3.0.1-offline-acceptance`。当前 Release Gate：**NOT_COMPLETE**。本冻结提交 FastAPI 回归为 **381 passed**、12 个子断言，v3 manifest/preflight 为 478/478、8/8；浏览器现场 24/24、Java/MySQL 30/30、故障注入 36/36、Durable 32/32 通过（各类 `environment_blocked=0`）。本轮不调用 DeepSeek；deterministic/replay 展示链通过，但不作为真实模型泛化证据。

提交 `5bfdc3c7c8eb88f76abecc6ea063eb2173880813` 的远程 `mall-ci` 与 `quality-evaluation` 均实际 success：[`mall-ci`](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34821813055)、[`quality-evaluation`](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34821813117)。候选批次报告位于 `tmp/deepseek-v3.0.1-candidate.json`（SHA-256 `1a6e0016fdc5116ea68690e14167f5351391cd75bd827abe613953196f7cd9d2`，本地忽略，不提交原始载荷）。唯一事实源：[`current-release-facts.json`](current-release-facts.json)；本轮结果：[`v3.0.1-offline-and-live-acceptance.md`](v3.0.1-offline-and-live-acceptance.md)。

本轮证据提交 `bd3a5cf787f87e2819c73021fc9a356c6c65da85` 的远程门禁已真实通过：[`mall-ci`](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34931831197)、[`quality-evaluation`](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34931831222)。

旧 releaseId `v3.0-deepseek-flash-final` 的锁保持不变；本轮新候选锁为 [`deepseek-release-lock-v3.0.1.json`](deepseek-release-lock-v3.0.1.json)，记录 `candidate-5f1d90208743` 失败和 0 provider requests，不允许无授权重跑。

历史 `e0c8b36` 的首次 `mall-ci` 曾因 OSV 容器无法解析 Java 本地 `1.0-SNAPSHOT` reactor 而失败（退出码 127）；后续工作流已改为 `--no-resolve` 并继续扫描显式 Python/npm lockfile 与 `mall2` POM 直接依赖。该过程属于历史 CI 审计，不代表当前 SHA 已远程通过；当前推送后必须以 GitHub 返回的最新结果为准。

## 历史审计记录（以下内容不代表当前 Commit）

## 当前权威结论（2026-09-12）

运行时代码提交：`52d5482455e2389cfd6c2ef15d233712607ffa9f`；证据推送提交：`efd3dcdd5d9c628a98b697ad63b57fe78b932cd9`；分支：`main`。工作区在本次运行开始时除 Git 忽略的 `tmp/` 外干净。本机合成 Release Gate：**通过**；证据提交对应的远程 Actions 也已通过：[`mall-ci` run 34646346032](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34646346032)、[`quality-evaluation` run 34646346115](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34646346115)。

## 门禁矩阵

| 门禁 | 结果 | 证据/范围 |
| --- | --- | --- |
| FastAPI 回归 | **362 passed / 0 failed** | `.venv/Scripts/python.exe -m pytest -q`，exit 0；1 条第三方弃用警告、7 子断言 |
| v3 deterministic | **478/478；代表性 8/8** | manifest/preflight，合同模式、无模型/无写入 |
| Live model main | **72/72** | 24 Case × 3，DeepSeek + synthetic read-only gateway |
| Live model holdout | **36/36** | 独立 12 Case × 3，非生产泛化率 |
| Grounding | **15/15；57/57 checks** | 当前 grounding runner，成本未配置 |
| Java | **portal 12/12；admin 6/6；Spring 1/1** | 显式 `-DskipTests=false`；Spring smoke 指向本地 Compose MySQL |
| Web | **passed** | `npm run build` |
| Docker/Compose | **8/8 + 8/8 healthy** | 主栈与隔离 fault 栈，Engine 29.7.2 |
| 现场 Runner | **122/122** | browser 24、Java/MySQL 30、fault 36、durable 32 |

## 报告指纹

- 现场报告：`tmp/field-acceptance-final/field-20260911T203212Z-95f5755e/field-acceptance.json`；SHA-256 `a0fbcd5c22638be8be480ae08344596a14d7874eafcd65194242b3f4df8c803e`。
- Fixture：`tmp/field-fixture.json`；SHA-256 `d4829bd272dad498b17890b24595c288150ed89d4f59b062424b70067513e093`。
- 主 live：`mall-ai-service/tmp/final-agent-quality-main-final5-20260912.json`；SHA-256 `b4041b3541e125b48e4b1114ff1e100aeeb6c40bea29f426d048850414be87d2`。
- Holdout：`mall-ai-service/tmp/final-agent-quality-holdout-final4-20260912.json`；SHA-256 `822775b454e921dc50817f764783ddd14fc65910e267b27aa2e559ecc5869612`。
- Grounding：`mall-ai-service/tmp/final-grounding-20260912.txt`；SHA-256 `fb90a00cdb4b835270126600190eb175ae13583db97b678080452c8be252d715`。

## 历史失败与处理

- 旧的 122 `environment_blocked` 报告是 Docker Desktop/Fixture 阻断，已被 Docker 恢复后的当前提交现场报告 superseded；不能与 122/122 相加。
- live main-final2/3/4 的 70/72、71/72 失败保留在 [最终失败矩阵](final-agent-failure-matrix.md)，当前通过来自通用 Runtime/Prompt 修复后的新报告，不是删除 Case 或放宽断言。
- Build 14A 退货状态资格拒绝被保留为真实 Java 资格负向边界；未伪造成功。

## 不能宣称

本 Gate 仅覆盖本机合成数据、DeepSeek 合成只读网关和本地 Docker 现场。没有真实支付、仓储、物流、维修系统；不能宣称生产 SLA/QPS、真实用户准确率、模型成本或线上部署。上游 `macrozheng/mall` 基础能力不归为个人原创。
# v3.0.1 最终在线验收门禁（2026-09-15）

**当前结论：NOT_COMPLETE。** 代码冻结 `06ef600e51e7b0dc362d43a98e274c28144738d8`；分支 `codex/v3.0.1-offline-acceptance`。离线就绪检查 24/24 通过，当前 SHA 的本机合成现场 122/122 通过，但唯一正式 DeepSeek 候选在第一条展示链失败，锁定为 `FAILED`，不得重试。

| Gate | 结果 | 证据 |
| --- | --- | --- |
| FastAPI | **382 passed / 0 failed** | `.venv/Scripts/python.exe -m pytest -q`，exit `0` |
| Java | portal **14/14**；Spring **1/1** | Maven `-DskipTests=false`，exit `0` |
| Web | **passed** | `npm run build`，exit `0` |
| Compose | **8/8 healthy** | `docker compose config --quiet`、健康状态 |
| v3 deterministic | **478/478；8/8** | manifest/preflight，无模型、无业务写入 |
| 现场 Runner | **122/122** | browser 24、Java/MySQL 30、fault 36、durable 32；合成数据 |
| DeepSeek candidate | **FAILED** | `candidate-226cdd440e85`；第一展示链失败，后续套件未执行 |
| GitHub Actions | **待当前 SHA 远程验证** | 本轮 GitHub 443 推送超时；旧 run 不并入 |

## DeepSeek 候选边界

正式报告：`tmp/deepseek-v3.0.1-final-06ef600e51e7b0dc362d43a98e274c28144738d8.json`，SHA-256 `6615d069122cb66ee8f3467f98ae79457ef287afd6f19c5e56035c45fb0b65c8`。Release lock：`docs/evidence/deepseek-release-lock-v3.0.1-final-06ef600e51e7b0dc362d43a98e274c28144738d8.json`，SHA-256 `f6efe1612697bec6ba55505d83acdd320c1db044dc89f4e276891e32517b2a36`。

候选报告在第一条 `main_open_task_closed_loop` 展示链停止；clarify/pause/resume、fact-change、main 24×3、supplemental 12×3 和 Grounding 均为 `not_executed`。共享跨进程账本观察到 9 个 Provider metadata events（9 成功、0 失败、27,329 tokens），但主机入口未设置 `MALL_RELEASE_LEDGER_PATH`，锁/报告自身记录为 0；两者差异按失败证据公开，绝不后处理为“通过”。这些请求不能推导任务准确率、成本或泛化能力。

## 当前现场证据

报告：`tmp/offline-field-acceptance/field-20260915T064300Z-99f3dc2f/field-acceptance.json`，SHA-256 `ec337708baa422fcd11bf2ac2334372e88f3592f4dde454ab0f674413704122b`，`testedCodeCommit=06ef600e51e7b0dc362d43a98e274c28144738d8`。就绪报告：`docs/evidence/v3.0.1-live-readiness.json`，SHA-256 `e559244e6c9a14689d15b44d4203070f4a6ed8fc9660ed2cbaaa24ab7b380614`。现场只使用合成账号、订单和政策；fault 组中本地安全停止/隔离 Compose 的合同场景不代表外部供应商宕机。

当前不生成 live GIF，也不更新 README 为“真实模型通过”。禁止宣称生产部署、真实用户自然语言准确率、生产 SLA、真实支付/仓储/物流/维修履约或真实模型成本。
