# 测试与演示证据

## 2026-09-04 — 公开演示截图刷新与本机复验（本地提交 `10bce84284c4ba344e7880fac5a605958e4c4b90`）

本节对应本轮提交的前端示例占位符和三张真实页面截图。截图由本机 Compose 页面、Chrome headless/CDP 和合成账号生成；未保存或输出密码、Token、完整订单号、客户原话、RAG 原文或生产 Trace。提交已在本地完成，但当前网络无法连接 GitHub Git 端点，尚未推送；**不能使用历史 Actions 链接替代本次远程验证**。

| 范围 | 实际命令/动作 | 结果 |
| --- | --- | --- |
| FastAPI 全量 | `mall-ai-service/.venv/Scripts/python.exe -m pytest -q` | **346 passed**、1 条第三方弃用警告、7 个参数化子断言通过 |
| 质量合同 | `scripts/run_quality_agent_evaluation.py` | `quality-agent.v2` **17/17 passed** |
| Chunk/Metadata | `scripts/evaluate_chunk_metadata.py --summary` | `rag-chunk-metadata.v1` **8/8 passed**，合成 chunk `5`，外部模型调用 `0` |
| RAG 2.0 | `scripts/evaluate_rag2.py --summary` | Dense、Hybrid、Hybrid+Rerank 各 **52/52 passed**；外部模型调用 `0`；Dense 仍为默认，其他模式只保留实验 |
| v3 清单 | `validate_v3_release_manifest.py --json` | `478` deterministic、`36` live case、`12` performance profile；清单和 fixture hash 校验通过 |
| v3 预检 | `run_v3_release_preflight.py --json` | **478/478** deterministic、**8/8** representative runtime |
| Java portal | 受影响协同/事件/安全合同定向 Maven 测试 | **14/14 passed**，无失败、无跳过 |
| Java admin | 运营分析定向 Maven 测试 | **6/6 passed**，无失败、无跳过 |
| Web | `mall-ai-web/npm run build` | `vue-tsc --noEmit` 与 Vite build 成功 |
| Compose | `docker compose --env-file .env.example config --quiet` | 成功；常驻容器随后均为 healthy |
| 浏览器现场截图 | 真实 Chrome headless/CDP，客户/运营/质量页面各一张 | 三张 PNG 已生成并人工检查公开字段；这不是完整浏览器 E2E 清单 |

本轮新截图文件：

- `docs/assets/customer-policy-conversation.png`
- `docs/assets/operations-handoff-overview.png`
- `docs/assets/quality-evaluation-dashboard.png`

本节的本机结果不代表 GitHub Actions 已通过，也不代表生产部署、生产 SLA、真实用户准确率或真实外部履约系统接入。推送后必须等待该提交对应的 `mall-ci` 与 `quality-evaluation`，再补录远程链接；截至记录时远程仍停留在父提交 `8891d4c3fc5116aed794b76daca7e45e691795db`。

## 2026-09-04 — Build 22 提交后最终复验（`f88fee38b2089a0cc433650480ebac6dc3dcba03`）

这次只引用该提交对应的真实远程运行，不用旧提交的绿色结果替代：

| 工作流 | 真实运行 | 结果 | 范围 |
| --- | --- | --- | --- |
| `mall-ci` | [33841952626](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/33841952626) | **success** | Python、Java、Web、Compose contract、dependency-and-secret-risk 五个 job |
| `quality-evaluation` | [33841952630](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/33841952630) | **success** | 质量、任务编排、RAG 合同和开发者质量页面构建 |

本机分项复验（计数不相加）为：

| 范围 | 实际结果 |
| --- | --- |
| FastAPI + v3 deterministic | `346 passed`、`7 subtests passed`；manifest `478/478`，代表性 Runtime `8/8` |
| Quality / task / RAG contracts | quality-agent `17/17`；task orchestration `11/11`；RAG 合同 `55/55`；Chunk/Metadata `8/8` |
| Live model synthetic | 36 Case × 3 次 = **108/108 passed**；p95 `1438 ms` |
| Java | portal `14/14`；admin `6/6` |
| Web / Compose | `npm run build` 成功；`docker compose --env-file .env.example config --quiet` 成功 |

Live-synthetic 只使用脱敏、版本化合成输入和安全任务摘要；模型不可用时 runner 会返回 `ENVIRONMENT_BLOCKED`，不会转成通过。浏览器 E2E 24 条和 Java/MySQL 30 条 manifest 场景仍未逐条现场执行；已有真实网站代理、Java 定向测试和 Docker health 证据应与这些合同清单分开理解。

## GitHub Actions 远程 CI（2026-09-03，代码验证基线 `d7c8f9bf4354f05009b9f83c793a3f296619bf66`）

| 工作流 | 真实运行 | 结果 | 范围 |
| --- | --- | --- | --- |
| `mall-ci` | [33746095478](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/33746095478) | **success** | Python、Java、Web、Compose contract、dependency-and-secret-risk 五个 job 均 success |
| `quality-evaluation` | [33746095446](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/33746095446) | **success** | 质量合同、任务编排、RAG 合同与开发者页面构建 job success |

远程 workflow 的具体命令以 [.github/workflows/ci.yml](../.github/workflows/ci.yml) 和 [.github/workflows/quality-evaluation.yml](../.github/workflows/quality-evaluation.yml) 为准。本机等价命令的分项结果为：FastAPI `343 passed`、`7 subtests passed`；Java portal `13/13`、admin `6/6`；Vue `npm run build` 成功；OSV v2 直接清单扫描无未处理结果；遗留 Java 8 风险例外及到期日见 `osv-scanner.toml`。远程 job 的 success 与本机数量分开记录，不能相加。

## Mall v3.0 发布预检（2026-09-03，本机 deterministic）

| 范围 | 实际结果 | 口径 |
| --- | --- | --- |
| v3 manifest | `478` 条 deterministic、`36` 条 live synthetic、`12` 个性能 Profile；hash 校验通过 | 只验证清单完整性，不把 live/E2E/Java 现场冒充已运行 |
| v3 release preflight | **478/478** 注册 Case、**8/8** 代表性 Runtime 分支通过 | 无真实模型、无业务写入 |
| 新增回归测试 | `tests/test_release_manifest.py` + `tests/test_release_evaluation.py`：**23 passed**（与全量计数分开） | 覆盖重复 ID、fixture 篡改、跳过开关、空断言和运行时失败码 |
| CI 接线 | `ci.yml` 与 `quality-evaluation.yml` 均先 compile/collect，再执行 manifest/preflight | 本次提交后的远程运行已通过，链接见上方 |

命令：

```powershell
Push-Location .\mall-ai-service
.\.venv\Scripts\python.exe scripts\validate_v3_release_manifest.py --json
.\.venv\Scripts\python.exe scripts\run_v3_release_preflight.py --json
Pop-Location
```

该节不改变下方历史 Build 证据；计数不能相加，也不代表生产部署、生产 SLA 或真实用户模型泛化。

更新时间：2026-09-02。本文件只记录本机实际执行的命令和结果；所有账号、订单、凭据、Token、内部 payload 与 Docker 卷均未写入本文档。

> 说明：本文件保留最终升级阶段的一轮较广产品验收快照。公开发布准备阶段另有一轮最小复核，使用的定向测试选择不同，结果见 [公开发布记录](PUBLIC_RELEASE_RECORD.md)。两组计数不能相加，也不代表生产验收。

## 任务感知 Agent 一次性升级复验（2026-09-02）

本节只记录本次任务编排改造后的新增复验，不覆盖或重算前文其他 Build 的历史结果。现场保留已有命名卷和演示数据，未执行 `docker compose down`、卷删除或数据库清空。

| 范围 | 实际结果 |
| --- | --- |
| FastAPI 全量回归 | **317 passed，7 subtests passed**；1 条 Starlette/httpx 第三方弃用警告。 |
| Vue 生产构建 | `npm run build`：`vue-tsc --noEmit` 与 Vite build 成功。 |
| Java portal 定向 | **22/22 passed**；无失败、无跳过。 |
| Java admin 定向 | **14/14 passed**；无失败、无跳过。 |
| Compose 静态合同 | `docker compose config --quiet` 成功。 |
| 任务编排 contract_mock | `task-orchestration.v1` **11/11 passed**；仅合成 TurnPlan 与内存会话状态，零模型/Redis/Java/RAG/业务写入。 |
| 任务编排真实模型合成评测 | `task-orchestration.v1` **10/10 passed**；仅 P0 + 版本化合成消息/安全任务摘要，总 **23.1 s**、p95 **4.0 s**；不访问真实会话或业务服务。 |
| Docker 重建 | `docker compose up -d --build mall-ai-service mall-ai-web` 成功；依赖服务按需重建/重启，八个常驻服务最终 healthy。 |
| 任务感知网站代理 | 合成匿名会话：缺标识诊断为 `active` → 政策临时切题为 `paused` → 重启 `mall-ai-service` → 同会话自然恢复为 `active`；每步 HTTP 200。 |
| 公开字段安全 | 代理响应只含公开 DTO；未出现 `intent`、`rag_sources`、`rag_context`、`tool_result`、`trace`、task/checkpoint 内部标识等禁止字段。 |

本次代理冒烟验证的是任务状态和公开边界，不是登录后的 Java 写入或完整售后建单现场；后者沿用前文已有的独立验收记录。

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
| Build 21 Durable 恢复（历史快照） | `MALL_BUILD21_BOOTSTRAP_LOCAL_DEMO=true` 的 `verify_build21_authenticated_live.py` 通过。 | 该脚本记录的是 Build 21 的 Durable checkpoint 验收；本次任务感知升级的缺标识路径已改为普通 `waiting_input` 任务，不再把 `interrupt()` 作为默认客户行为。 |
| 统一售后 | `MALL_UNIFIED_BOOTSTRAP_LOCAL_DEMO=true` 的 `verify_unified_after_sales_live.py` 通过。 | 显式自举的 A/B 合成账号经 Vue 代理完成政策询问、确认卡、Java 建单、查询进度、取消待确认动作、幂等目标和 B 无法读取 A 的申请；公开 DTO 未泄露内部字段。 |
| MCP 只读互操作 | `verify_mcp_authenticated_live.py` 通过。 | `initialize → tools/list → get_order_summary → SSE readiness` 成功；匿名、跨账号复用 session、跨账号订单、`memberId` 参数注入和已关闭 session 均被拒绝；无写工具。 |

以上本地脚本仅在显式 opt-in 时通过 Java 公共演示 API 创建新的合成账号、地址、订单及（统一售后脚本中的）售后/事件记录；脚本不输出其标识或凭据，也没有删除原有数据。

## 尚未宣称完成的项

- `live_model_synthetic` 已在本轮手动执行并通过 3 条合成案例；它不是 CI、客户请求或线上模型泛化评测，且 Provider 未返回可用 Token 数，不能据此声称成本或普遍准确率。
- `.github/workflows/ci.yml` 与 `quality-evaluation.yml` 的本次远程运行已成功；后续提交仍需重新查看对应 Actions，不能把一次成功外推为所有未来版本都通过。
- 本机 Docker/合成数据/定向测试不证明生产部署、独立安全审计、真实支付/仓储/物流/维修接入、生产 QPS/P95/SLA 或模型对所有输入的准确率。

## 复验命令

```powershell
cd C:\Users\12969\Desktop\mall\mall-ai-service
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
