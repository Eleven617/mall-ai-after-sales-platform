# 测试与演示证据

更新时间：2026-09-01。本文件只记录本机实际执行的命令和结果；所有账号、订单、凭据、Token、内部 payload 与 Docker 卷均未写入本文档。

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
- `.github/workflows/ci.yml` 与 `quality-evaluation.yml` 已具备本地可审查质量门，但本根目录当前不是 Git 仓库，且没有本轮远程 GitHub Actions 运行记录。
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
