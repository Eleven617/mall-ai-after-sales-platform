# 当前工作进度记录

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
