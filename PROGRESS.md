# 当前工作进度记录

更新时间：2026-09-04（Asia/Shanghai）
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

### 已跟踪、当前有改动

- `mall-ai-web/src/App.vue`：将输入框 placeholder 中的完整订单号示例改为泛化文本。
- `docs/assets/customer-policy-conversation.png`：截图脚本曾写入过新文件，但当前内容仍需重新确认，不能直接作为公开最终截图。
- `docs/assets/operations-handoff-overview.png`：由真实运营页面重新截图，使用合成账号/聚合数据。

### 未跟踪但被 Git 忽略的临时文件

- `tmp/capture_demo_screenshots.py`：仅用于本地截图驱动，已多次调整；位于被 `.gitignore` 忽略的 `tmp/`，不应提交。
- `tmp/capture-chrome-profile*`：Chrome 临时 profile，不应提交。

### 尚未修改

- `docs/assets/quality-evaluation-dashboard.png` 本轮尚未成功刷新，仍是旧截图。
- `README.md`、`docs/TEST_AND_DEMO_EVIDENCE.md`、`docs/PUBLIC_RELEASE_RECORD.md` 和其他公开证据文档尚未针对本轮截图更新完成。

## 3. 已执行的命令和结果

以下命令均未输出或保存密码、Token 或密钥：

| 命令/动作 | 结果 |
| --- | --- |
| `npm run build`（`mall-ai-web`） | 成功：`vue-tsc --noEmit` 与 Vite build 均通过 |
| `docker compose up -d --build mall-ai-web` | 成功；Web 及依赖服务重建/重启完成，未 down、未删卷 |
| `docker compose ps` | 八个常驻服务显示 healthy |
| 本地截图脚本（多次） | 部分失败：客户页异步历史/消息状态等待条件未稳定；运营页截图已生成；质量页未刷新 |
| 本地 API 冒烟（合成客户） | 登录、创建会话、发送政策问题均 HTTP 200；只检查响应结构/长度 |
| `view_image` 检查三张资产 | 已查看；发现客户图仍可能显示旧 placeholder 中的完整数字，不能发布；运营图为合成只读概览；质量图为旧的真实质量页截图 |
| `git status --short --branch` | 当前分支 `main`；改动为 App.vue 与两张截图；临时脚本/profile 被忽略 |

## 4. 当前遇到的问题

1. 客户截图脚本中，服务端请求已返回 200，但前端在登录后的会话历史异步更新与新消息渲染之间存在竞态；脚本观察到客户页只有两行消息，未稳定捕获 assistant 回答，因此等待条件超时。
2. 客户截图当前仍能看到旧的完整数字订单号 placeholder；在重新生成并用图像检查确认前，不能提交或在 README 宣称它是安全新截图。
3. 质量截图尚未刷新；上一次质量图虽来自真实页面，但不是本轮截图更新，且页面中的合同字段名不能被误判为真实敏感值，需用更精确的安全检查重新截取。
4. 公开证据文档中的历史提交 SHA、远程 Actions 链接、Java 分项数量和 live-synthetic p95 有不同历史口径；恢复后必须以一组新命令和新提交统一，不得编数字或把旧链接冒充新提交结果。
5. 本轮尚未完成公开文档同步、最终全量回归、Git commit/push 和新提交对应的远程 Actions 验证。

## 5. 尚未完成的任务

- 稳定生成并检查三张真实截图：客户、运营、质量；确认无完整订单号、密码、Token、客户原话、RAG 原文或生产 Trace。
- 重新运行与本轮改动相关的测试，至少包括 Vue build、`git diff --check`、FastAPI 受影响测试；交付前按仓库规则完成 FastAPI 全量回归，并复跑 Compose config。
- 更新 `README.md`、`docs/TEST_AND_DEMO_EVIDENCE.md`、`docs/PUBLIC_RELEASE_RECORD.md`（必要时同步 v3 证据），写清日期、命令、数据集规模、hash、deterministic/contract_mock/live_model_synthetic/浏览器现场边界。
- 检查暂存区，确保没有 `.env`、密码、Token、模型权重、Chroma 索引、浏览器 profile、日志或其他敏感文件。
- 创建专门的截图/测试证据 commit，建议消息：`docs: refresh live demo screenshots and evaluation evidence`。
- 推送到 `origin main`，等待该新提交对应的 `mall-ci` 与 `quality-evaluation` 完成；只有真实 success 才能在最终报告写新 Actions 链接和“该提交 CI 通过”。
- 若远程失败，逐项读取新日志并如实记录根因、命令和阻塞点，不能沿用旧成功链接。

## 6. 下一步应该做什么

1. 先修复临时截图脚本的客户页竞态：等待登录初始化结束后再发送，或打开已生成且不含业务标识的合成政策会话；必要时用 CDP 检查 DOM 状态，但不要打印页面敏感内容。
2. 重新截三张图并逐张 `view_image` 检查；客户图若仍有数字订单号，立即判为不合格并重截，不做图像伪造或遮盖替代。
3. 运行测试和静态检查，保存真实输出。
4. 只更新公开文档中的真实结果与边界，不把历史数量相加、不把 mock 说成真实模型效果。
5. 检查 Git diff/status 后提交、推送，再等待并记录新 Actions。

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
- `git push origin main` 及一次连接参数重试均因 `github.com:443` connection reset/timeout 失败；SSH 推送因当前环境无可用 public key 被拒绝。GitHub API 核对显示远程仍为 `8891d4c3fc5116aed794b76daca7e45e691795db`，尚未生成本次提交的 Actions 运行。
- 当前下一步：网络/认证通道恢复后推送 `10bce84`，等待新提交对应的 `mall-ci`/`quality-evaluation`，再将真实链接和最终 SHA 补回证据文档；在此之前不能宣称远程 CI 成功。
