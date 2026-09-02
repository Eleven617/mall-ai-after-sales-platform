# 公开发布记录

更新时间：2026-09-02。本文记录本仓库公开发布准备阶段实际完成的工作，严格区分已验证事实、已知边界和待补材料。账号密码、API Key、Token、真实订单、真实客户对话、Docker 卷和本地模型/索引均不在仓库或本文中。

## 发布范围

- 公开仓库：`Eleven617/mall-ai-after-sales-platform`。
- 发布内容：可复现的本地合成演示代码、文档、测试与启动脚本。
- 不包含：真实生产数据、密钥、预构建的 Chroma 索引、本地 Embedding/Reranker 权重、Docker 命名卷、日志或浏览器会话数据。
- 视频演示：有意留待后续制作；当前仓库已经提供文字演示脚本，不将“视频已完成”作为发布结论。

## 2026-09-02：公开 CI 收口证据

提交 [`c5ad321355a5c9979ada83f72294c70440964cc8`](https://github.com/Eleven617/mall-ai-after-sales-platform/commit/c5ad321355a5c9979ada83f72294c70440964cc8) 已在 GitHub `main` 真实触发并通过两个独立工作流：

- [`mall-ci` 成功运行 #33607689472](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/33607689472)：Python、Java 8、Vue、Compose 静态合同、Gitleaks 与 OSV 直接依赖/锁文件门禁均为成功。
- [`quality-evaluation` 成功运行 #33607689443](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/33607689443)：合成 `contract_mock`、质量 Agent 合同、RAG 2.0 合同、Chunk/Metadata 合同与开发者质量页面构建均为成功。

这两条远程结论与本机结果不能混为同一组数字。为尽量接近 GitHub Ubuntu runner，本次还在临时的 Python 3.12 / Maven 3.9 + Temurin 8 容器中复跑了下列命令；没有使用工作区 `.venv`、Chroma 索引、本地模型、模型 Key、数据库或客户数据：

| 范围 | 干净环境实际结果 |
| --- | --- |
| Python 自动化回归 | `291 passed, 20 subtests passed`。 |
| 独立 LangGraph 学习实验 | `9` 条确定性 `unittest` 通过；升级后的 `langgraph==1.2.11` 仍覆盖最大步数、非法动作、暂停/恢复与事实泄露边界。 |
| 质量 Agent 合同 | `quality-agent.v2`：`17/17`；独立 pytest 合同：`20 passed`。 |
| RAG 2.0 合同 | `55 passed`；不运行真实模型，也不改变 Dense 默认结论。 |
| Chunk / Metadata 合同 | `rag-chunk-metadata.v1`：`8/8`，`0` 外部模型调用。 |
| Java 8 | `mvn -pl mall-portal,mall-admin -am -DskipTests package` 成功；portal 定向 `13 passed`，admin 定向 `6 passed`。 |
| Web | 隔离 Node 22 容器中 `npm ci && npm run build` 成功；远程工作流另以 Node 20 成功构建。 |
| Compose 静态合同 | `docker compose config --quiet` 成功；未启动、重建或删除 Compose 服务/卷。 |

### 依赖与密钥扫描范围

- Gitleaks 仍为远程必过门，不使用 `continue-on-error`、`|| true` 或忽略规则伪造通过。
- OSV 远程门逐一扫描所有 Maven 模块 POM 的**直接依赖声明**、三个 Python requirements 文件和 npm lockfile；`mall2` 的本地 `SNAPSHOT` reactor 坐标不能在 OSV 的隔离容器中解析，因此不把解析错误伪装成扫描成功，也不宣称这是完整传递依赖 SBOM 扫描。
- `langgraph` 实验 pin 已从 `0.6.11` 升至 `1.2.11`，CI pytest 固定为已修复公告 `GHSA-6w46-j5rx-g56g` 的 `9.0.3`；Java 直接依赖同步升至可兼容的最新 Java 8 线版本。
- `osv-scanner.toml` 保留三条可见、带到期日的 Java 8 风险接受项：`GHSA-5m4m-73w9-8433`、`GHSA-5vpf-xvv7-c8vh`、`GHSA-9fw2-h3hf-293r`。Spring Data 2.7.18 没有同线修复；控制器合同测试仅降低受影响绑定面，并不是完整修复。必须在 `2027-09-02` 前迁移到 Spring Boot 3 / Java 17 或重新作出有证据的处理。

因此，可如实表述为“GitHub CI 的当前直接依赖/锁文件安全门和回归门已通过”，不能表述为“所有传递依赖零风险”或“已完成独立安全审计”。

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
2. GitHub Actions 的当前远程证据见上节两个成功运行；它覆盖 CI 所列回归、构建、Compose 静态合同、质量合同与直接依赖/锁文件扫描，不能替代 Java 全量集成测试、完整传递依赖 SBOM 审计或独立安全审计。
3. 本地 Docker 验收保留已有命名卷和合成演示数据；没有清库、删卷、删历史日志或模拟外部支付/仓储/物流/维修成功。
4. 真实模型调用需要由使用者在本机配置自己的密钥和可达网络；无模型配置时系统会安全停止模型相关请求，仍可做结构与权限验证。
5. 清理后的 `main` 不再包含旧认证值的可达提交；已经获取过旧提交的本地克隆、缓存或镜像不受 Git 历史重写控制。若该旧值曾在某个真实环境中有效，应由该环境维护者单独轮换对应的认证签名/会话密钥。

## 复现入口

从干净克隆启动、设置本机演示身份和运行验证命令见根目录 [README](../README.md) 与 [测试与演示证据](TEST_AND_DEMO_EVIDENCE.md)。公开前仍应按 [公开前检查清单](PUBLIC_RELEASE_CHECKLIST.md) 完成维护者自己的许可证和敏感信息复核。
