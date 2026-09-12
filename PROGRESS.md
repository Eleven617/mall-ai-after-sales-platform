# 当前工作进度记录

## 2026-09-12｜最终公开收口当前状态

- 运行时代码基线：`9c7c29045c28446b16a609768cd4b4c1202f8a51`，分支 `main`；本轮不再扩展业务功能。
- 最新真实本机证据：FastAPI 365；DeepSeek 主集 72/72；补充评测集 36/36（非独立盲测）；Grounding 15/15、57/57 checks；Java portal core 12/12 + compatibility 2/2、admin 6/6、Spring 1/1；Vue build；deterministic 478/478、代表性 8/8；现场 browser 24/24、Java/MySQL 30/30、fault 36/36、durable 32/32，共 122/122。
- 当前唯一事实源：`docs/evidence/current-release-facts.json`；公开素材证据：`docs/evidence/final-showcase-evidence.md`；自动一致性门禁：`scripts/validate_public_release.py`。
- 已更新 README 的最终演示素材、supplemental 口径、FastAPI/Java 结果；`mall-ai-service/tmp/` 已精确忽略，临时报告保留在本机不提交。
- 待完成的发布动作只有：运行本地最终门禁、提交/推送公开文档和素材、等待该新 SHA 的 `mall-ci` 与 `quality-evaluation`，然后把 CI URL 回填事实源。远程 CI 未完成前不称为最终远程通过。

## 历史记录（以下内容不代表当前 Commit）

更新时间：2026-09-04（Asia/Shanghai；恢复执行后最终核对）
仓库：`C:\\Users\\12969\\Desktop\\mall`
分支：`main`
开始本轮时 HEAD：`8891d4c3fc5116aed794b76daca7e45e691795db`
远程：`https://github.com/Eleven617/mall-ai-after-sales-platform.git`

> 本文件是暂停点记录。它不保存密码、Token、API Key、订单号、客户原话、原始工具载荷或完整 Trace。

## 1. 已完成的工作

### 本轮已完成

- 已阅读并核对当前 README、公开证据文档、前端页面和截图驱动脚本的现状。
- 将客户页面输入框中的完整数字订单号示例改为泛化示例，避免公开页面继续提示业务标识。
- 使用真实本地 Compose 页面、真实 Chrome headless/CDP 和本地合成账号尝试更新三张公开截图。
- 发现截图驱动脚本的运营/质量登录选择器过窄，已在临时脚本中修正；同时加入缓存禁用、独立浏览器 profile 和更严格的真实凭据/长业务编号检查。
- 重新执行 Vue 生产构建：成功。
- 执行 `docker compose up -d --build mall-ai-web`：成功；未执行 `docker compose down`，未删除命名卷或清空数据库。依赖服务被 Compose 正常重建/重启后恢复健康。
- 通过直接本地 API 冒烟确认：合成客户登录、创建会话和政策消息请求均返回 HTTP 200；响应包含安全回答字段（只记录字段长度，不记录回答内容）。

### 之前已经存在、但本轮没有重新测量的证据

以下数字来自此前提交/证据文档，仅作为基线，不能替代本轮最终复验：

- v3 manifest：`478/478`；deterministic preflight：`478/478`；代表性 Runtime：`8/8`。
- 质量 Agent contract_mock：`17/17`。
- 任务编排 contract_mock：`11/11`；live_model_synthetic：`10/10`，blocked `0`。
- v3 live synthetic：`36` 个 Case × `3` 次，共 `108/108`；此前不同记录中的 p95 数值不一致，需在恢复后以实际运行日志重新核对。
- FastAPI：`346 passed`、`7` 个参数化子断言通过。
- Chunk/Metadata：`8/8`；RAG grounding contract：`15/15`；RAG verifier：`36` 条通过；RAG 2.0 黄金集：`52` 条，Dense/Hybrid/Hybrid+Rerank 均通过，Dense 继续默认。
- Java portal/admin、Vue、Compose 和 Docker health 均有此前通过记录；不同历史文档对 Java 分项数量也存在口径差异，恢复后应重新执行并统一记录。
- 旧提交已有成功的 GitHub Actions 运行链接，但它们不是本轮新截图/新代码提交的验证结果，恢复后不得直接沿用为新提交证据。

## 2. 修改过的文件

### 已提交并推送（当前最终进度）

- `mall-ai-web/src/App.vue`：将输入框 placeholder 中的完整订单号示例改为泛化文本。
- `docs/assets/customer-policy-conversation.png`：真实客户政策对话截图，合成数据。
- `docs/assets/operations-handoff-overview.png`：真实运营转人工概览截图，合成聚合数据。
- `docs/assets/quality-evaluation-dashboard.png`：真实质量评测页面截图，合成评测数据。
- `README.md`：同步公开演示截图与可信性边界。
- `docs/TEST_AND_DEMO_EVIDENCE.md`：记录本机复验、截图 hash 和远程 Actions 证据。
- `docs/PUBLIC_RELEASE_RECORD.md`：记录公开发布范围与验证边界。
- `docs/evidence/v3.0-release-evidence.md`：同步最新已验证提交与远程门禁链接。
- `PROGRESS.md`：记录暂停点、恢复结果和最终远程验证状态。

### 未跟踪但被 Git 忽略的临时文件

- `tmp/capture_demo_screenshots.py`：仅用于本地截图驱动，已多次调整；位于被 `.gitignore` 忽略的 `tmp/`，不应提交。
- `tmp/capture-chrome-profile*`：Chrome 临时 profile，不应提交。

本轮没有遗留的截图或公开证据文件改动；工作区状态以 `git status` 为准。

## 3. 已执行的命令和结果

以下命令均未输出或保存密码、Token 或密钥：

| 命令/动作 | 结果 |
| --- | --- |
| `npm run build`（`mall-ai-web`） | 成功：`vue-tsc --noEmit` 与 Vite build 均通过 |
| `docker compose up -d --build mall-ai-web` | 成功；Web 及依赖服务重建/重启完成，未 down、未删卷 |
| `docker compose ps` | 八个常驻服务显示 healthy |
| 本地截图脚本（修正等待条件后） | 成功生成并检查客户、运营、质量三张真实 PNG |
| 本地 API 冒烟（合成客户） | 登录、创建会话、发送政策问题均 HTTP 200；只检查响应结构/长度 |
| `view_image` 检查三张资产 | 三张均通过公开安全检查；无完整订单号、密码、Token 值、客户原话、RAG 原文或生产 Trace |
| `git status --short --branch` | `main...origin/main`，工作区干净；临时脚本/profile 被忽略 |

## 4. 当前遇到的问题

1. 历史证据章节仍保留各自时间点和命令口径；这些记录不能与当前结果相加。
2. 生产 SLA、真实用户泛化、真实外部履约和完整浏览器/Java-MySQL manifest 仍属于未验证边界，详见公开证据文档。

## 5. 尚未完成的任务

本轮必做任务已全部完成：三张真实截图、公开证据文档、本机复验、提交、推送，以及最终进度提交对应的两个 GitHub Actions 工作流均已成功。

## 6. 下一步应该做什么

本轮已收口。下一次重大升级时，先读取本文件和仓库 `AGENTS.md`，仅针对新增改动运行受影响测试，再提交并等待新的远程 Actions；不要把本次本机/合成结果宣传为生产能力。

## 7. 不能重复执行或不能删除的内容

- 不执行 `git reset --hard`、`git checkout --`、`docker compose down`、`docker compose down -v`、卷删除、数据库清空或迁移回滚；必须保留现有本机演示数据和命名卷。
- 不删除既有测试、EvalCase、工作流 job、扫描门禁或历史证据来制造绿色结果；不使用 `continue-on-error`、`|| true`、跳过测试或放宽断言。
- 不删除或覆盖与本任务无关的用户脏改动；只保留本轮明确改动。
- 不提交 `.env`、密码、Token、私钥、真实手机号/地址/订单号、完整客户对话、生产 trace、RAG 原文、模型权重、Chroma 索引、日志和 Chrome profile。
- 不把旧提交的 Actions success 当作新提交 success；不在远程验证完成前添加或宣称新的绿色 CI 证据。
- 不重复运行会新增业务数据的现场自举脚本，除非先确认其幂等/影响范围并确有必要；截图优先使用只读页面或已存在的合成数据。
- 不启动 Build 20 新 RAG/Hybrid/Rerank 主线，也不新增第四个 Agent或学习支线；当前暂停点只针对截图、证据、测试和 Git 收口。

## 恢复执行后的新增记录（2026-09-04）

- 已修正临时截图脚本的客户页等待条件，使用真实 Chrome headless/CDP 成功生成并检查三张 PNG：客户政策对话、运营转人工概览、AI 质量评测页面。
- 三张图均未发现完整数字订单号、密码、Token 值、客户原话、RAG 原文或生产 Trace；质量页中出现的 `token`/`rag_context` 等仅是合同测试中的字段名说明，不是实际值。
- 重新执行本机复验：FastAPI `346 passed`；质量 `17/17`；Chunk/Metadata `8/8`；v3 manifest `478/478`、preflight `478/478`、代表性 Runtime `8/8`；RAG2 三种模式各 `52/52`；Java portal `14/14`、admin `6/6`；Vue build、Compose config 均成功。
- 已更新 `README.md`、`docs/TEST_AND_DEMO_EVIDENCE.md`、`docs/PUBLIC_RELEASE_RECORD.md`，明确本轮截图与本机结果；已创建本地提交 `10bce84284c4ba344e7880fac5a605958e4c4b90`。
- 初次 `git push` 曾受网络重置影响；网络恢复后，`10bce84` 及证据状态提交 `c6be3ea3c7b2c2fef9893815a444e06430b02ddd` 已推送。
- 该 SHA 的 `mall-ci` run `33866949872` 与 `quality-evaluation` run `33866949829` 均为 GitHub 实际 `success`。链接已同步到公开证据文档。
- `df67753` 已推送并完成对应远程复验：`mall-ci` run `33868598584`、`quality-evaluation` run `33868598567` 均为 success。
- 随后为修正文档暂停状态创建并推送提交 `d1718a25fab537da65b3f333b910386e99315055`；该提交对应 `mall-ci` run `33869631046` 和 `quality-evaluation` run `33869631166`，两者均为 GitHub 实际 `success`。Web job 的依赖安装曾长时间运行，最终正常通过。
- 又创建进度记录提交 `42d0385ca5549f228b39a776b06808488ab9160f`，随后补充网络阻塞记录为 `96bec5e3f9df48b204a85a22f4c67c18bb25ea06` 并成功推送。该最终远程 SHA 对应 `mall-ci` [33870716875](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/33870716875) 和 `quality-evaluation` [33870716971](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/33870716971)，两者均为 success。
- 最终进度收口提交 `e9e6c425eb2aa50791b8be791df1db82d6385bc2` 已推送；对应 `mall-ci` [33870889803](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/33870889803) 和 `quality-evaluation` [33870889792](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/33870889792)，两者均为 success。
- 文档状态对齐提交 `bd9012e3ad6c05c3385f6aba24aacf14ec191981` 已推送；对应 `mall-ci` [33871171081](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/33871171081) 和 `quality-evaluation` [33871171148](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/33871171148)，两者均为 success。
- 后续仅对本文件做了进度状态校正；最终进度提交已推送，且其对应的 `mall-ci` 与 `quality-evaluation` 均已由 GitHub 实际判定为 success。核心代码、截图和公开证据已在此前提交中完成并远程验证。

## 2026-09-05 — 当前 HEAD 剩余关键结果补测

- 当前代码 HEAD：`38cf3809e48ec08bead6accc07a4ace27ebf5f59`；补测开始时 `origin/main` 仍为 `cbb951f9815b7483d2aeec0620947fdb1eba59b0`。
- 已新增当前 HEAD 分层证据：`docs/evidence/v3.0-current-head-evidence.md` 与 `docs/evidence/v3.0-current-head-evidence.json`。
- 当前确定性结果：FastAPI `349 passed`；v3 `478/478` + 代表性 Runtime `8/8`；Quality Agent `17/17`；任务编排 `11/11`；Chunk/Metadata `8/8`；RAG verifier `36/36`；Dense/Hybrid/Hybrid+Rerank 各 `52/52`；Java portal/admin `14/14`、`6/6`；Web build、Compose config、Compose endpoint `3/3` 通过；Docker `8/8 healthy`。
- 当前真实模型合成补测：开放任务 Agent `24` 案例 × `3` 次 = `24 passed / 48 failed / 0 environment_blocked`；报告为被忽略的 `tmp/live_model_agent_runtime_report_current_head.json`。Grounding `15` 条 = `11 passed / 4 quality_failed / 0 environment_blocked`；4 条 `UNAPPROVED_EVIDENCE_SOURCE` 保留为失败证据。
- 完整浏览器 E2E `24`、Java/MySQL integration `30`、fault injection `36`、durable async recovery `32` 本轮未逐条现场执行；因缺少一次性本地账号/订单环境变量，7 个现场脚本均标为 `environment_blocked`，没有把 manifest 注册数当作通过数。
- 已完成：证据文件通过 `git diff --check` 并提交推送；验证提交 `9fba15ddac537016fca2116286e7238121b1236a` 对应 `mall-ci` [33901002046](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/33901002046) 与 `quality-evaluation` [33901002043](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/33901002043) 均为 GitHub 实际 success。
- Grounding 已重新执行并保存为被忽略的 `tmp/rag2_grounding_current_head.json`（SHA-256 `f254dea3c765251ae49385a3f6c1fd93276b474717f040557b8c7a57093cf0be`）：`11 passed / 4 quality_failed / 0 environment_blocked`，Token `20,550`，p95 `2,098.64 ms`；4 条 `UNAPPROVED_EVIDENCE_SOURCE` 原样保留。

## 2026-09-07 — 前端统一展示升级与 GitHub 发布收口复核

- 前端代码发布 Commit：`ddb466489dffcb2bec0ec15151e8cb0121518691`，分支 `main`；随后仅补充本次发布证据文档。
- 已完成前端统一展示升级：客户页三栏工作台、开放任务 Agent 状态/时间线/事实产物/行动卡、运营摘要卡、人工协同步骤条、质量评测摘要与折叠详情，详见 `docs/evidence/frontend-unified-upgrade.md`。
- 实际构建命令：`Push-Location .\mall-ai-web; npm run build; Pop-Location`，`vue-tsc --noEmit` 与 Vite build 均通过，退出码 `0`。
- `git diff --check` 通过；`docker compose config --quiet` 通过。
- 已新增并提交前端需求说明 `docs/FRONTEND_UNIFIED_UPGRADE_SPEC.md` 与验收记录 `docs/evidence/frontend-unified-upgrade.md`；没有修改后端 API、Java 写入、权限、数据库、Outbox 或评测契约。
- 当前 Docker Desktop 进程虽已请求启动，但 Docker Linux 引擎未就绪：`docker info` 与 `docker compose ps` 无法连接 `dockerDesktopLinuxEngine`。因此本轮未重新生成升级后的真实截图，也没有把旧截图冒充新截图。
- `ddb4664` 已成功推送到 `origin/main`。该 SHA 对应的 GitHub Actions 均已实际成功：[`mall-ci` run 34114651785](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34114651785)、[`quality-evaluation` run 34114651788](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34114651788)。
- GitHub 仓库公开状态、Description 和 11 个 Topics 已通过 GitHub API 核对；没有修改个人主页、仓库可见性或创建新仓库。

### 当前发布门禁

本次“GitHub 发布收口”状态为**部分完成，尚未完全通过**：代码、README、前端构建、远程推送、当前 SHA 的 Actions 和仓库 About 信息已完成；但升级后的 `agent-task-workspace.png` 及三张最终现场截图尚未在当前 Docker 环境重新生成，因此不能称为全部发布收口完成。

## 2026-09-08 — Docker 恢复与前端现场最终收口

- Docker Desktop 已恢复可用。仅隔离运行时 socket/secret-engine 目录并让 WSL `main` 目录重建，未删除 `D:\DockerData\DockerDesktopWSL\disk\docker_data.vhdx`、镜像、容器、命名卷或演示数据；Docker Engine `29.7.2`。
- `docker compose config --quiet` 通过；`docker compose up -d --no-build` 后八个常驻服务均为 `healthy`。
- 已用真实 Chrome headless/CDP 和合成页面重新生成四张公开截图：`customer-policy-conversation.png`、`agent-task-workspace.png`、`operations-handoff-overview.png`、`quality-evaluation-dashboard.png`。尺寸与 SHA-256 记录见 `docs/evidence/frontend-unified-upgrade.md` 和 `docs/TEST_AND_DEMO_EVIDENCE.md`。
- README、前端发布说明和现场证据已同步“截图已重新生成”的事实；临时脚本仍在被忽略的 `tmp/`，不提交。
- 截图、README 和前端证据已提交为 `4dae57fc8d0876fb2b343f898489750f8b95c4ab` 并推送；该 SHA 的 `mall-ci` run `34179749694` 与 `quality-evaluation` run `34179749709` 均为 GitHub 实际 `success`。本次待办仅剩将本段状态同步提交并验证该同步提交的 Actions。
- 本次现场可证明本地合成演示和展示边界；不证明完整浏览器 E2E、Java/MySQL 全量集成、真实支付/仓储/物流/维修、真实模型泛化或生产 SLA。此前“Docker 未就绪/截图未生成”的段落是当时状态，已由本节后续现场结果 supersede，不删除历史记录。

## 2026-09-08 — 现场补测与发布收口续记

- Docker Engine `29.7.2` 可用；Redis、RabbitMQ 单容器重启后等待恢复，最终 Compose `8/8 healthy`、endpoint `3/3`。
- 真实 Chrome/CDP 截图脚本退出码 `0`，四张合成数据截图已刷新；未提交临时密码、Token、订单号或 `tmp/` 临时脚本。
- 一次性本地现场批次：权限双账号、统一售后创建/确认/查询/取消、Build 21 首次重启恢复、MCP 只读隔离、人工协同入队/领取/补件/处理/结案均退出码 `0`。
- Java/MySQL `MallPortalApplicationTests` 使用被忽略的临时 Compose 配置 `1/1` 通过；默认 `localhost:3306` 配置因 `Public Key Retrieval is not allowed` 失败，未修改正式配置。
- Build 14A 退货状态脚本退出码 `1`：当前合成订单不满足 Java `return_refund` 资格；Build 21 后续两次独立重跑退出码 `1`，错误为 `waiting diagnosis task is missing or malformed`。失败均保留，未放宽断言。
- 完整 manifest 的 browser `24`、Java/MySQL `30`、fault `36`、durable recovery `32` 没有独立逐条现场执行器，继续标记 `environment_blocked`；不能把 deterministic `478/478` 写成这些现场套件通过。
- 本次新增/修改工作区文件：四张 `docs/assets/*.png`、`docs/evidence/v3.0-current-head-evidence.md/.json`、`docs/TEST_AND_DEMO_EVIDENCE.md`、`docs/PUBLIC_RELEASE_RECORD.md`、`mall-ai-service/scripts/verify_return_status_flow.py`。待完成：运行最终校验、提交、推送、等待 Actions 并回填当前 SHA。
- 已提交并推送 `dbbd18c029acf8bacc21cada2c161da15185cc42`（`test: record live release gate verification`）。对应 `mall-ci` [34200061061](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34200061061) 与 `quality-evaluation` [34200061063](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34200061063) 均为 GitHub 实际 `success`。
- 证据同步已提交并推送 `73d12c5ecde9c56a21ce7be78e194d8fbc1e837c`；该 SHA 的 [`mall-ci` run 34204868188](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34204868188) 与 [`quality-evaluation` run 34204868215](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34204868215) 均为 GitHub 实际 `success`。完整 24/30/36/32 现场清单仍属环境阻塞，不得宣传为通过。

## 2026-09-08 — Docker 恢复后最终复验（本次续记）

- 最终复验时 Docker Desktop 再次因 Windows 内部 AF_UNIX/reparse socket 残留退出；已将 Docker 内部 `run`/Secrets Engine 运行时目录改名保留为 `.stale.manual`，并确认未执行 factory reset、`docker compose down`、卷/VHDX 删除或数据库清空。Docker Engine `29.7.2` 恢复。
- `docker compose up -d mall-ai-service mall-ai-web` 完成后，MySQL、Redis、Mongo、RabbitMQ、mall-portal、mall-admin、mall-ai-service、mall-ai-web 共 `8/8 healthy`；`scripts/verify_compose_stack.py` exit `0`，Vue/FastAPI/Java readiness `3/3`。
- 恢复后的现场批次重新执行：权限双账号、统一售后创建/确认/列表/状态/取消/跨账号、Build 21 同会话重启恢复、MCP 只读隔离、人工协同均 exit `0`。Build 14A 退货状态仍 exit `1`，当前合成订单被 Java `return_refund` 资格拒绝，未伪造通过。
- 本次本机确定性复验：FastAPI `349 passed`、7 subtests；Vue `npm run build` 成功；v3 manifest/preflight `478/478`、代表性 `8/8`；Compose config、`git diff --check` 均通过。
- 公开证据已同步到 `docs/evidence/v3.0-current-head-evidence.md/.json`、`docs/TEST_AND_DEMO_EVIDENCE.md`、`docs/PUBLIC_RELEASE_RECORD.md`。这些文档仍明确：完整 browser `24`、Java/MySQL `30`、fault `36`、durable recovery `32` 没有逐条独立现场执行器，继续 `environment_blocked`；deterministic `478/478` 不能代替现场套件。
- 当前无需用户补充授权；下一步提交并推送本次证据同步，等待该新 SHA 的 `mall-ci` 与 `quality-evaluation`，然后以真实结果交接。

## 2026-09-09 — 统一现场 Runner 当前提交复核

### 已完成

- 新增并提交统一现场入口 `scripts/Verify-FieldAcceptance.ps1`，底层 Runner 为 `mall-ai-service/scripts/verify_field_acceptance.py`；它按 manifest 自动发现 browser 24、Java/MySQL 30、fault 36、durable 32 条 Case，并为每条结果保存 runner/execution 状态、failure class、Commit、Fixture hash、断言、依赖、trace 摘要和证据路径。
- 新增 `mall-ai-service/scripts/field_browser_support.py`、`verify_build14_eligibility_live.py` 与 `tests/test_field_acceptance.py`；故障 Runner 已收紧为先验证服务确实停止，再验证启动后健康，避免仅凭命令退出码判定通过。
- 当前代码提交：`45f842f9ed6c0a9b636e0420fe489312e71a28fb`，已推送到 `origin/main`。
- 当前提交确定性复验：FastAPI `353 passed`、`7 subtests passed`；Runner 合同 `11 passed`；manifest/preflight `478/478`、`8/8`；Vue build、Compose config、Java portal `14/14`、admin `6/6` 均通过。
- 当前提交现场入口已真实启动并生成报告：`tmp/field-acceptance/field-20260909T074151Z-d56eb7fe/field-acceptance.json`，SHA-256 `7da1d8efdd399d354ea535d32f9c24f9405508f5c57f9cb3364223219487e32a`；四类 Runner `122/122 ready`，本轮 `0 passed / 122 environment_blocked`，Release Gate 未通过。
- Docker 阻断已定位到 Docker Desktop 后端 `sailor-ingest.sock` 重命名 `error 1920`；未执行 factory reset、全局清理、卷/VHDX 删除或数据库清空。
- README、`docs/evidence/v3.0-current-head-evidence.md`、`docs/TEST_AND_DEMO_EVIDENCE.md`、`docs/PUBLIC_RELEASE_RECORD.md` 已同步当前 SHA、命令、报告 hash、旧报告 stale 规则和真实边界。

### 旧报告与当前结果的边界

- 2026-09-08 曾在旧提交 `314f5d9` 的 Docker/Chrome/Compose 环境中执行并得到 browser `24/24`、Java/MySQL `30/30`、durable `32/32`、fault `36/36`（fault 报告 Gate 因 Fixture 未绑定而为 false）。这些报告保留为历史证据，但因 Commit 与当前不一致已标为 stale，不能与当前结果相加，也不能写成当前 Release Gate 通过。
- Build 14A 正/负资格验证器已实现；此前一次旧提交运行通过，但当前 SHA 尚未在 Docker 恢复后重跑，因此不扩大为当前 Gate 通过。

### 下一步

1. Docker Desktop 修复后，以当前 `45f842f` 重新运行 `scripts\\Verify-FieldAcceptance.ps1`，必须绑定一次性合成 Fixture，并确认 122 条均不再 `environment_blocked`。
2. 重新运行 Build 14A 正/负验证，保存当前 SHA 报告；随后更新三份公开证据并再跑 `git diff --check`。
3. 只在当前 SHA 的现场报告 Gate 通过后，才可在 README/简历写“当前提交的 122 条现场 Case 通过”；当前只能写“统一 Runner 已实现，确定性门禁通过，现场复验受 Docker 环境阻断”。

### 不能做

- 不能把 `45f842f` 的当前 `environment_blocked` 改写成 passed；不能把旧 `314f5d9` 报告与当前结果合并。
- 不能删除失败/阻断记录、降低断言、用 deterministic `478/478` 代替现场 122 条，或用 `docker compose down -v`、删卷、删 VHDX、factory reset 解决 Docker。

## 2026-09-09 — Netty 安全修复与 Docker 外部阻塞收口

### 已完成

- `mall2/pom.xml` 将 Netty 从 `4.1.136.Final` 升级到 `4.1.137.Final`，针对 GitHub `dependency-and-secret-risk` 报告的 `GHSA-c4c3-7fpv-j4q5`（CVSS 9.1）和 `GHSA-fccg-mwvh-qqg4`（CVSS 6.9）完成根因修复；未关闭扫描、未跳过测试。
- 当前代码提交 `38601904595b6ae82a1e692d88c33d83d1ba1e01` 已推送。远程 [mall-ci run 34333690241](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34333690241) 与 [quality-evaluation run 34333690290](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34333690290) 均为 GitHub 实际 `success`。
- 本机复验：Java portal `14/14`、admin `6/6`（显式 `-DskipTests=false`）；FastAPI `353 passed`；Vue build、Compose config 通过。修复后的本地 OSV 识别 0 个受影响包，但因本地 SNAPSHOT 模块不可解析退出 `127`，不替代远程门禁结论。
- 现场 Runner 报告仍真实记录 `122 environment_blocked`；此前现场报告与当前提交不一致，已标 stale。Docker Desktop 后端错误为 `sailor-ingest.sock` Windows `error 1920`，本轮停止重复重试，未 factory reset、未删卷/VHDX/数据库。

### 当前未完成与下一步

- 当前 v3.0 Release Gate **未通过**：需要先由 Windows/Docker Desktop 层修复该 IPC 文件错误，再以当前提交、一次性合成 Fixture 重新运行 `scripts\\Verify-FieldAcceptance.ps1`。
- 未运行出有效的当前提交 `browser 24`、`Java/MySQL 30`、`fault 36`、`durable 32` 逐条现场结果；不能把 deterministic `478/478`、远程 CI success 或旧提交现场报告当作替代。
- 本轮没有修改业务 API、数据库契约、测试预期或公开安全边界；没有新增敏感文件。

## 2026-09-09 — Docker 恢复后的完整现场验收收口

### 已完成

- Docker Desktop/Linux Engine `29.7.2` 已恢复；主 Compose `docker compose up -d --no-build` 后 8/8 常驻服务 healthy，`verify_compose_stack.py` exit `0`、readiness `3/3`。
- 启动隔离 fault Compose 项目 `mall-field-20260909`，8/8 服务 healthy；故障停止/恢复只作用于该隔离项目。
- 使用当前 HEAD `84e111d17e4117287660421ea5772a9ddcf44382` 和新的合成 Fixture（SHA-256 `7573e19271528e904d2eb40cef2765f05d4e5f489f2b35cc1b1359bcd5128759`）完整执行现场 Runner。
- 最新报告：`tmp/field-acceptance/field-20260909T105750Z-12222b15/field-acceptance.json`，SHA-256 `6a301cd28072ebbf01fa07e81d7aaf5c4b2de9741c14ceb351122cac18f21567`。
- 当前现场结果：browser `24/24`、Java/MySQL `30/30`、fault `36/36`、Durable recovery `32/32`，合计 **122/122 passed、0 failed、0 environment_blocked**；Release Gate **passed**。
- 第一轮因旧随机账号 Fixture 导致 Java `30 environment_blocked`，已保留为 superseded 证据；没有与最终通过数相加，也没有放宽断言。

### 当前边界

- 本轮没有修改业务代码、测试预期、Java API 或数据库契约；只更新本地忽略的现场报告和待提交的证据文档。
- 122/122 只证明当前机器、当前 Docker/Chrome、当前合成 Fixture 的现场路径；不宣称生产 SLA、真实用户泛化、真实支付/仓储/物流/维修接入。
# 2026-09-09｜最终现场补测与交接前复核（最新）

- 网络已恢复；`origin/main` 与本地 `main` 在复核开始时一致，当前基线为 `5ea119970a2a4a9a9194dc3e1e46eff412bd406e`，工作区干净。
- Docker Engine `29.7.2` 正常；主 Compose 和隔离 fault Compose 均启动，主服务/隔离服务各 `8/8 healthy`，`verify_compose_stack.py` readiness `3/3`。
- 最新现场 Runner 报告 `tmp/field-acceptance/field-20260909T105750Z-12222b15/field-acceptance.json`（SHA-256 `6a301cd28072ebbf01fa07e81d7aaf5c4b2de9741c14ceb351122cac18f21567`），运行时代码绑定 `84e111d17e4117287660421ea5772a9ddcf44382`，合成 Fixture SHA-256 `7573e19271528e904d2eb40cef2765f05d4e5f489f2b35cc1b1359bcd5128759`。
- 四类现场结果：browser `24/24`、Java/MySQL `30/30`、fault `36/36`、durable recovery `32/32`；合计 `122/122 passed`、`0 failed`、`0 environment_blocked`。此前旧 Fixture 导致的阻断报告仅作为 superseded 证据保留。
- Build 14A 最新重跑：`tmp/run_build14.ps1` → `verify_build14_eligibility_live.py`，退出码 `0`；负资格拒绝、正资格通过、第二账号隔离、同幂等键复用和事务性 Outbox 均通过。密码只存在进程环境。
- 当前只剩证据交接：补齐 `docs/final-handoff/` 八份文件，提交并推送；然后等待该文档提交对应的 `mall-ci` 与 `quality-evaluation` 真实结果。运行时代码没有新增修改。

## 2026-09-12｜最终技术负责人收口（当前记录）

### 已完成

- 运行时代码基线为 `52d5482455e2389cfd6c2ef15d233712607ffa9f`，本轮没有删除测试、放宽断言、关闭扫描或修改业务数据库契约。
- 全量 FastAPI 回归 **362 passed**、1 条第三方弃用警告、7 个子断言；Vue `npm run build` 通过；Java portal 定向 **12/12**、admin **6/6**；`MallPortalApplicationTests.contextLoads` 使用临时 Compose MySQL 配置 **1/1**。
- v3 manifest/preflight **478/478、8/8**；Grounding **15/15、57/57 checks**；DeepSeek live synthetic 主集 **72/72**、holdout **36/36**，均无禁止副作用和重复最终写入。
- Docker Engine `29.7.2` 已恢复；主栈与隔离 fault 栈各 8/8 healthy。当前合成 Fixture 绑定的现场 Runner 报告为 `tmp/field-acceptance-final/field-20260911T203212Z-95f5755e/field-acceptance.json`，四类合计 **122/122 passed、0 failed、0 environment_blocked**。
- 已新增/更新最终事实包：`docs/evidence/final-agent-quality-baseline.md/.json`、`final-agent-failure-matrix.md`、`v3.0-current-head-evidence.md/.json`、`release-gate-summary.md`、`resume-fact-pack.md/.json`，并同步 README、测试证据、公开发布记录和 claim matrix。

### 证据指纹

- 现场报告 SHA-256：`a0fbcd5c22638be8be480ae08344596a14d7874eafcd65194242b3f4df8c803e`。
- 合成 Fixture SHA-256：`d4829bd272dad498b17890b24595c288150ed89d4f59b062424b70067513e093`。
- 主 live 报告 SHA-256：`b4041b3541e125b48e4b1114ff1e100aeeb6c40bea29f426d048850414be87d2`；holdout：`822775b454e921dc50817f764783ddd14fc65910e267b27aa2e559ecc5869612`。

### 已完成的远程交付

- 证据已提交并推送：`efd3dcdd5d9c628a98b697ad63b57fe78b932cd9`；该 SHA 对应的 [`mall-ci` run 34646346032](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34646346032) 与 [`quality-evaluation` run 34646346115](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34646346115) 均为 `success`。
- `tmp/` 下的运行报告被 Git 忽略，不提交原始报告/密码/Token；公开仓库只提交脱敏摘要和 hash。

### 下一步

1. 校验 JSON、`git diff --check` 和当前工作区。
2. 提交证据与 README 更新，推送 `main`。
3. 等待并核对该 SHA 对应的 `mall-ci`、`quality-evaluation`；只在真实成功后更新远程 CI 结论。

### 不可扩大

- 122/122 是当前机器、本地 Docker/Chrome 和合成 Fixture 的现场证据，不是生产 SLA 或真实用户泛化。
- 没有真实支付、仓储、物流、维修系统；不能宣称外部履约成功。
- 上游 `macrozheng/mall` 的商城基础能力不归为个人原创。
