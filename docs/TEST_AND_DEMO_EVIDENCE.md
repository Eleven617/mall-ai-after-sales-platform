# 测试与演示证据

更新时间：2026-09-02。本文件只记录实际执行的命令和结果；所有账号、订单、凭据、Token、内部 payload 与 Docker 卷均未写入本文档。

> 说明：本文件保留最终升级阶段的一轮较广产品验收快照。公开发布准备阶段另有一轮最小复核，使用的定向测试选择不同，结果见 [公开发布记录](PUBLIC_RELEASE_RECORD.md)。两组计数不能相加，也不代表生产验收。

## 2026-09-02：真实网页截图与本地演示入口

本机 Docker Compose 的网站代理页面由 Edge 无头浏览器实际打开并截图；使用合成身份 `localDemoCustomerA`、`localDemoOperations`、`aiQualityDeveloper`，没有读取或保存浏览器已有会话。截图文件为：

| 文件 | 页面与可见证据 |
| --- | --- |
| [`docs/assets/customer-policy-conversation.png`](assets/customer-policy-conversation.png) | 客户政策咨询；公开回答可见，RAG 内部字段不可见。 |
| [`docs/assets/operations-handoff-overview.png`](assets/operations-handoff-overview.png) | 运营转人工概览；窗口、去重总数、类别次数和百分比由后端聚合。 |
| [`docs/assets/quality-evaluation-dashboard.png`](assets/quality-evaluation-dashboard.png) | 质量页面；`contract_mock` 版本化合成评测显示 17/17。 |

三张图均为 1440×1000 PNG，数据为本机合成数据，不是生产数据或线上用户截图。视频演示仍未制作。

本轮还修复并验证了 Windows PowerShell 5.1 下的 `Initialize-LocalDemoAccess.ps1`：Docker SQL 不再依赖容易被原生参数拆分的引号脚本，Python 哈希程序通过标准输入执行，脚本源文件使用 UTF-8 BOM 以保留中文合成标签。新增 `tests/test_local_demo_access_script_contract.py` 防止该入口回归；本机 `-DryRun` 与实际本地身份边界验证通过。

### 与本次展示更新对应的远程 CI

提交 [`0d407783fec9291b3d8d5d01befc38c0e009c553`](https://github.com/Eleven617/mall-ai-after-sales-platform/commit/0d407783fec9291b3d8d5d01befc38c0e009c553) 已实际通过 [`mall-ci` #33613512109](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/33613512109) 和 [`quality-evaluation` #33613512012](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/33613512012)。

| 本机命令范围 | 实际结果 |
| --- | --- |
| `python -m pytest -q` | 292 passed，20 subtests passed。 |
| `run_quality_agent_evaluation.py` / 质量 pytest | 17/17；20 passed。 |
| CI RAG pytest / Chunk summary / LangGraph unittest | 55 passed；8/8；9 tests passed。 |
| `npm run build` / Java CI 定向 Maven / Compose 合同 | 全部成功；portal 13 passed，admin 6 passed。 |

远程 `mall-ci` 的 Python、Java、Web、Compose contract、dependency-and-secret-risk 5 个 Job 均为 success；质量工作流的隔离 Job 为 success。计数分别记录，不能相加。由于本机 Docker 当时没有 Docker Hub HTTPS 代理，额外的本机 Gitleaks 镜像拉取被环境阻塞；没有将该本机步骤描述为成功，远程安全 Job 才是当前安全门的真实成功证据。

## 公开 CI 收口（2026-09-02）

本节是与下方历史本机/Docker 快照分开的新证据。提交 [`c5ad321355a5c9979ada83f72294c70440964cc8`](https://github.com/Eleven617/mall-ai-after-sales-platform/commit/c5ad321355a5c9979ada83f72294c70440964cc8) 的远程 GitHub Actions 已成功：[`mall-ci` #33607689472](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/33607689472)、[`quality-evaluation` #33607689443](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/33607689443)。

| 证据类型 | 运行范围 | 实际结果与含义 |
| --- | --- | --- |
| 远程 GitHub CI | Ubuntu runner，Python 3.12、Java 8、Node 20 | `mall-ci` 全部 5 个 job 成功：Python、Java、Web、Compose contract、dependency-and-secret-risk。远程成功才证明工作流在 GitHub runner 上可运行。 |
| 远程质量门 | Ubuntu runner，合成夹具 | `quality-evaluation` 成功：只运行 `contract_mock` / 合同/RAG/Chunk 测试和 Web 构建；不调用真实模型。 |
| 干净 Python 回归 | 临时 `python:3.12-slim` 容器 | `python -m pytest -q`：**291 passed，20 subtests passed**。未使用 `.venv`、Chroma、模型、模型 Key 或数据库。 |
| 质量 Agent 合同 | 同一干净 Python 容器 | `run_quality_agent_evaluation.py`：**17/17**；指定质量 Agent pytest：**20 passed**。 |
| RAG 合同 | 同一干净 Python 容器 | 指定 RAG 2.0 pytest：**55 passed**；Chunk/Metadata：**8/8**，0 外部模型调用。此处不是 52 题真实模型准确率结论。 |
| LangGraph 兼容性 | 干净 Python 容器 | `python -m unittest discover -s labs/langgraph_order_exception -p "test_*.py" -v`：**9 tests passed**；防止安全升级后的实验图放宽工具/暂停边界。 |
| Java 8 | 临时 `maven:3.9.9-eclipse-temurin-8` 容器 | `package` 成功；portal 定向 **13 passed**，admin 定向 **6 passed**。普通 package 不再要求可达的远程 Docker daemon。 |
| Web | 隔离 Node 容器 + GitHub Node 20 | 本机隔离 Node 22：`npm ci && npm run build` 成功；GitHub Actions 另以 Node 20 成功。 |
| Compose 静态合同 | 本机 | `docker compose config --quiet` 成功；未启动/重建项目 Compose 服务。 |
| 密钥与依赖门 | GitHub + 本机等价 OSV 命令 | 远程 Gitleaks 与 OSV 均成功。OSV 范围是所有 Maven POM 的直接依赖声明、Python requirements 和 npm lockfile；详见 [公开发布记录](PUBLIC_RELEASE_RECORD.md#依赖与密钥扫描范围)。 |

上述项目分别计数，绝不相加为一个“总通过数”。本机隔离容器用于复现依赖/平台前提；远程 GitHub 成功是 CI 是否通过的唯一依据。

## 本次最终复验（2026-09-01）

以下是本次在现有命名卷与已健康 Compose 服务上重新执行的结果。现场验证使用进程内一次性合成账号和密码；它们没有被输出、保存或写入本文件。

| 范围 | 本次结果 |
| --- | --- |
| FastAPI 全量回归 | **287 passed，20 subtests passed**；仅 1 条第三方弃用警告。 |
| Vue 生产构建 | `vue-tsc --noEmit` 与 Vite 生产构建通过。 |
| Java portal | **22 tests passed**：统一售后、Outbox、人工案件与控制器边界。 |
| Java admin | **14 tests passed**：运营、质量开发者与人工处理角色边界。 |
| 质量/Chunk 评测 | `quality-agent.v2` **17/17**，`rag-chunk-metadata.v1` **8/8**。 |
| RAG 2.0 黄金集 | Dense、Hybrid、Hybrid + Rerank 均 **52/52**；本次 Dense p95 **20.51 ms**、Hybrid p95 **33.31 ms**、Hybrid + Rerank p95 **4311.78 ms**。Dense 继续保持默认。 |
| Docker/网站代理 | 八个常驻服务健康；网页、FastAPI、Java 与 MCP health 均为 HTTP 200。Build 21 重启恢复、统一售后与 MCP 只读网站代理均再次通过。 |
| 日志保护 | 八个常驻容器均使用 `json-file`，单容器上限为 **10 MB × 3**；本次没有删除现有卷、演示数据或历史日志。 |

## 自动化与构建验证

| 范围 | 实际命令 | 实际结果 |
| --- | --- | --- |
| FastAPI 全量回归 | `mall-ai-service/.venv/Scripts/python.exe -m pytest -q` | **287 passed, 20 subtests passed**；仅 1 条 Starlette/httpx 第三方弃用警告。 |
| Java portal 售后/Outbox/人工案件 | `mvn -pl mall-portal -am "-Dtest=AiCaseHandoffServiceImplTest,AiServiceCaseServiceImplTest,AiServiceCaseOutboxPublisherTest,AiServiceCaseEventReceiverTest,AiAfterSalesApplicationServiceImplTest,AiAfterSalesApplicationControllerTest" "-DskipTests=false" "-Dsurefire.failIfNoSpecifiedTests=false" test` | **22 tests passed**。 |
| Java admin 运营/开发者/人工处理权限 | `mvn -pl mall-admin -am "-Dtest=AiServiceOperationsServiceImplTest,AiServiceOperationsControllerTest,AiDeveloperControllerTest,AiAfterSalesReviewServiceImplTest,AiAfterSalesReviewControllerTest" "-DskipTests=false" "-Dsurefire.failIfNoSpecifiedTests=false" test` | **14 tests passed**。 |
| Vue | `npm run build` | `vue-tsc --noEmit` 与 Vite 生产构建均成功。 |
| Compose 静态合同 | `docker compose config --quiet` | 成功。 |
| 质量 Agent | `scripts/run_quality_agent_evaluation.py` | `quality-agent.v2`：**17/17 passed**；包括越权、敏感 handoff、工具失败、非法结构化动作、重复工具调用和运营编造数字反例。 |
| 真实模型合成评测 | `docker compose exec -T mall-ai-service python -c "...run_quality_evaluation(execution_mode='live_model_synthetic')..."` | `live-model-synthetic.v1`：**3/3 passed**；只使用版本化合成输入和模拟工具/聚合结果，本次运行约 **11.8 s**。Provider 未返回可用 Token 数，未虚构成本。 |
| Chunk/Metadata | `scripts/evaluate_chunk_metadata.py --summary` | `rag-chunk-metadata.v1`：**8/8 passed**，0 外部模型调用。 |
| RAG 2.0 | `scripts/evaluate_rag2.py --summary` | `rag2-golden.v1`：三种模式均通过 52 题合成黄金集；详见下表。 |
| MCP 安全合同 | `pytest -q tests/test_mcp_readonly_contract.py`（包含于全量） | 覆盖 Streamable HTTP session/SSE、主体隔离、只读工具、身份/URL/写参数、额外字段与过深参数拒绝。 |
| FR-19 人工协同网站代理 | `MALL_SERVICE_CASE_*` 仅在当前 PowerShell 进程设置后运行 `scripts/verify_service_case_live.py` | **通过**：客户诊断→Java 规则入队→人工处理人员登录/领取→请求补件→客户补件→人工处理/结案→客户公开时间线；B 账号不可见 A 案件。凭据未写入文件或本文档。 |
| 本地演示身份初始化 | `Initialize-LocalDemoAccess.ps1 -DryRun` | PowerShell 语法与真实 Compose MySQL 回滚事务通过；不提交任何账号、密码、订单或缓存改动。 |
| 本地自举输出隐私 | `pytest -q tests/test_bootstrap_live_demo.py`（包含于全量） | 标准输出只含状态和用户名；订单/会员标识只可经显式短生命周期结果文件供脚本内部读取，调用者随即删除。 |

### 本机 RAG 2.0 对比（52 条版本化合成黄金集）

| 模式 | Recall@3 | MRR | nDCG@3 | p95 延迟 | 结论 |
| --- | ---: | ---: | ---: | ---: | --- |
| Dense | 1.000000 | 0.948718 | 0.962147 | 19.11 ms | 保持默认：当前小型本地语料上排序指标最高。 |
| BM25 + Dense + RRF | 1.000000 | 0.935897 | 0.952683 | 28.93 ms | 保留为可复现实验，不替换默认。 |
| Hybrid + Cross-Encoder Rerank | 1.000000 | 0.935897 | 0.952683 | 4535.81 ms | 本机 CPU 延迟明显更高，且没有质量收益，不默认启用。 |

13 条无答案/拒答样例与 39 条有支持证据样例均在同一套件内。该结果只适用于当前本地政策语料、模型文件和运行环境；本地 CPU/磁盘成本未换算成人民币，也不代表生产准确率或 SLA。

## Docker 与网站代理现场验收

运行环境为根目录 Compose，未执行 `docker compose down`、卷删除或数据库清空。现场检查时 `mysql`、`redis`、`mongo`、`rabbitmq`、`mall-portal`、`mall-admin`、`mall-ai-service` 与 `mall-ai-web` 八个常驻服务均为 `healthy`；`mysql-migrate` 是一次性迁移服务，不作为常驻容器。

| 路径 | 实际结果 | 断言 |
| --- | --- | --- |
| Build 21 Durable 恢复 | `MALL_BUILD21_BOOTSTRAP_LOCAL_DEMO=true` 的 `verify_build21_authenticated_live.py` 通过。 | Vue 代理 → FastAPI → Java/Redis；缺订单号 interrupt、重启 `mall-ai-service`、Redis readiness、同会话恢复、重复恢复、A/B 跨账号拒绝；只读诊断未创建售后记录。 |
| 统一售后 | `MALL_UNIFIED_BOOTSTRAP_LOCAL_DEMO=true` 的 `verify_unified_after_sales_live.py` 通过。 | 显式自举的 A/B 合成账号经 Vue 代理完成政策询问、确认卡、Java 建单、查询进度、取消待确认动作、幂等目标和 B 无法读取 A 的申请；公开 DTO 未泄露内部字段。 |
| MCP 只读互操作 | `verify_mcp_authenticated_live.py` 通过。 | `initialize → tools/list → get_order_summary → SSE readiness` 成功；匿名、跨账号复用 session、跨账号订单、`memberId` 参数注入和已关闭 session 均被拒绝；无写工具。 |

以上本地脚本仅在显式 opt-in 时通过 Java 公共演示 API 创建新的合成账号、地址、订单及（统一售后脚本中的）售后/事件记录；脚本不输出其标识或凭据，也没有删除原有数据。

## 尚未宣称完成的项

- `live_model_synthetic` 已在本轮手动执行并通过 3 条合成案例；它不是 CI、客户请求或线上模型泛化评测，且 Provider 未返回可用 Token 数，不能据此声称成本或普遍准确率。
- 当前公开仓库的两条远程 Actions 已在本文件开头所列提交上成功；这不包含 Java 全量集成测试、完整传递依赖 SBOM 审计或独立安全审计。
- 本机 Docker/合成数据/定向测试不证明生产部署、独立安全审计、真实支付/仓储/物流/维修接入、生产 QPS/P95/SLA 或模型对所有输入的准确率。

## 复验命令

```powershell
cd C:\Users\12969\Desktop\mall\mall-ai-service
\.venv\Scripts\python.exe -m pip install -r requirements-ci.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\run_quality_agent_evaluation.py
.\.venv\Scripts\python.exe scripts\evaluate_chunk_metadata.py --summary
.\.venv\Scripts\python.exe scripts\evaluate_rag2.py --summary

cd C:\Users\12969\Desktop\mall\mall-ai-web
npm run build

cd C:\Users\12969\Desktop\mall\mall2
mvn -pl mall-portal -am "-Dtest=AiCaseHandoffServiceImplTest,AiServiceCaseServiceImplTest,AiServiceCaseOutboxPublisherTest,AiServiceCaseEventReceiverTest,AiAfterSalesApplicationServiceImplTest,AiAfterSalesApplicationControllerTest" "-DskipTests=false" "-Dsurefire.failIfNoSpecifiedTests=false" test
mvn -pl mall-admin -am "-Dtest=AiServiceOperationsServiceImplTest,AiServiceOperationsControllerTest,AiDeveloperControllerTest,AiAfterSalesReviewServiceImplTest,AiAfterSalesReviewControllerTest" "-DskipTests=false" "-Dsurefire.failIfNoSpecifiedTests=false" test

cd C:\Users\12969\Desktop\mall
docker compose config --quiet
docker compose ps
```
