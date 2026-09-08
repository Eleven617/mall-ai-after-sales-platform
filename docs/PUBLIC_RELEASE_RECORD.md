# 公开发布记录

## 2026-09-08 — Docker 运行时恢复后的最终现场复验

在最终补测前，Docker Desktop 因 Windows 残留 AF_UNIX/reparse socket 无法启动；已采用可恢复的内部运行时目录改名方案并重新启动，未执行 factory reset、`docker compose down`、卷/VHDX 删除或数据库清空。Docker Engine `29.7.2` 恢复后，Compose 8/8 常驻服务 healthy，`verify_compose_stack.py` 的 Vue/FastAPI/Java readiness `3/3` 通过。

恢复后的合成现场批次：双账号权限、统一售后创建/确认/列表/状态/取消/跨账号、Build 21 同会话重启恢复、MCP 只读隔离、人工协同均 exit `0`；Build 14A 退货状态 exit `1`，原因是当前合成订单被 Java `return_refund` 资格规则拒绝，未放宽断言或伪造通过。完整 `browser_e2e 24`、`java_mysql_integration 30`、`fault_injection 36`、`durable_async_recovery 32` 仍没有逐条独立现场执行器，继续标记 `environment_blocked`，不能由 deterministic `478/478` 代替。

本次结果和命令已同步到 [`v3.0 当前 HEAD 证据`](evidence/v3.0-current-head-evidence.md)；不宣称生产 SLA、真实用户泛化或真实支付/仓储/物流/维修接入。

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
