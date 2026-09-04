# 公开发布记录

## 2026-09-04 — 公开演示资产与本机复验更新（本地提交 `10bce84284c4ba344e7880fac5a605958e4c4b90`，远程验证待完成）

本轮更新了客户页面的泛化输入示例，并从真实本地 Compose 页面重新截取客户、运营和 AI 质量开发者页面。截图只使用合成账号与脱敏/聚合数据，不包含密码、Token、完整订单号、客户原话、RAG 原文或生产 Trace。

本机实际复验结果（不能代替远程 CI）：

- FastAPI 全量：`346 passed`，7 个参数化子断言通过；
- `quality-agent.v2`：`17/17 passed`；`rag-chunk-metadata.v1`：`8/8 passed`；
- v3 manifest/preflight：`478/478` deterministic，代表性 Runtime `8/8`；
- RAG2 Dense、Hybrid、Hybrid+Rerank：各 `52/52 passed`，Dense 继续默认；
- Java portal：`14/14`；Java admin：`6/6`；Vue 生产构建成功；Compose config 成功；八个常驻容器 healthy。

本节对应的代码、截图和文档变更已提交到本地，但 `git push` 因 `github.com:443` 网络连接重置/超时未完成；GitHub API 核对远程仍为父提交 `8891d4c3fc5116aed794b76daca7e45e691795db`。因此尚未取得新提交对应的 GitHub Actions 结果；推送后必须补录真实的 `mall-ci`、`quality-evaluation` URL，不能沿用旧提交链接。

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
