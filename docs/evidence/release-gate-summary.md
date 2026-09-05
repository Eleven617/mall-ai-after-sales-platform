# Mall v3.0 Release Gate 复核

复核时间：2026-09-05（Asia/Shanghai）  
当前 HEAD：`7f9cfb2d5171a88b2f6c5714f965e528c2543cc5`  
分支：`main`  
结论：**未通过**

“未通过”不是因为当前确定性门禁失败，而是因为发布门禁要求同时满足当前提交身份、远程验证和现场范围。本次当前 HEAD 尚未推送；最近成功的 `mall-ci` / `quality-evaluation` 对应旧提交 `94d782053c8ba188d2d79af0b3d5632ac685a8b8`，不能外推到当前 HEAD。另有 live model/Grounding 报告记录的是 `38cf380`，必须标为 stale；完整浏览器、Java/MySQL、故障注入和 durable recovery 清单也没有逐条现场执行。

## 当前提交和工作区

| 项目 | 结果 |
| --- | --- |
| `git status --short --branch`（生成事实包前） | `## main`，干净 |
| `git rev-parse HEAD` | `7f9cfb2d5171a88b2f6c5714f965e528c2543cc5` |
| `git branch --show-current` | `main` |
| `git diff --stat` | 空 |
| `git remote -v` | `https://github.com/Eleven617/mall-ai-after-sales-platform.git` |
| 与 `origin/main` | 本地领先 1 个提交，未推送 |
| 事实包写入后 | 仅本文件、`resume-fact-pack.md`、`resume-fact-pack.json` 为未提交文档改动 |

## 当前 HEAD 实际执行的命令

以下命令退出码均为 `0`，没有删除测试、skip、`continue-on-error` 或放宽断言：

```powershell
Push-Location .\mall-ai-service
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\validate_v3_release_manifest.py --json
.\.venv\Scripts\python.exe scripts\run_v3_release_preflight.py --json
.\.venv\Scripts\python.exe scripts\run_quality_agent_evaluation.py
.\.venv\Scripts\python.exe scripts\evaluate_task_orchestration.py --mode contract_mock
.\.venv\Scripts\python.exe scripts\evaluate_chunk_metadata.py --summary
.\.venv\Scripts\python.exe scripts\evaluate_rag2.py --summary
Pop-Location

Push-Location .\mall-ai-web
npm run build
Pop-Location

Push-Location .\mall2
mvn -pl mall-portal -am "-Dtest=AiCaseHandoffServiceImplTest,AiServiceCaseServiceImplTest,AiServiceCaseOutboxPublisherTest,AiServiceCaseEventReceiverTest,SpringDataWebExposureContractTest,MongoMicrometerCompatibilityTest" "-DskipTests=false" "-Dsurefire.failIfNoSpecifiedTests=false" test
mvn -pl mall-admin -am "-Dtest=AiServiceOperationsServiceImplTest,AiServiceOperationsControllerTest" "-DskipTests=false" "-Dsurefire.failIfNoSpecifiedTests=false" test
Pop-Location

docker compose --env-file .env.example config --quiet
```

结果分开统计：FastAPI `349 passed`；manifest/preflight `478/478`、代表性 Runtime `8/8`；Quality `17/17`；Task orchestration `11/11`；Chunk/Metadata `8/8`；RAG Dense/Hybrid/Hybrid+Rerank 各 `52/52`；Java portal `14/14`；Java admin `6/6`；Vue build passed；Compose contract passed。

## 远程 CI

历史成功运行确实存在，但不属于当前 HEAD：

- `mall-ci`：<https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/33901530634>，对应 `94d7820`，success。
- `quality-evaluation`：<https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/33901530719>，对应 `94d7820`，success。

当前 HEAD 没有新的远程运行链接。事实包没有把历史 success 写成当前 HEAD 的 CI 结论。

## 质量和现场缺口

| 范围 | 当前证据 | Gate 影响 |
| --- | --- | --- |
| live model open-task | 旧提交报告：24/72 passed，48 failed，0 blocked；报告 SHA `20e82406f4f8eceaf722dfc13249fe08f3d13e31b64eb791c122c54c7f112e0b` | stale，不能当当前 HEAD 通过；失败需保留。 |
| Grounding | 旧提交报告：11/15 passed，4 quality_failed，均 `UNAPPROVED_EVIDENCE_SOURCE`；报告 SHA `f254dea3c765251ae49385a3f6c1fd93276b474717f040557b8c7a57093cf0be` | 质量 Gate 未通过。 |
| browser E2E | manifest 注册 24，现场执行 0 | `environment_blocked` 24，不能宣称通过。 |
| Java/MySQL integration | manifest 注册 30，现场执行 0 | `environment_blocked` 30，不能宣称通过。 |
| fault injection | manifest 注册 36，现场执行 0 | `environment_blocked` 36，不能宣称通过。 |
| durable async recovery | manifest 注册 32，现场执行 0 | `environment_blocked` 32，不能宣称通过。 |
| 真实外部履约 | 支付/仓储/物流/维修未接入 | 只能写未接入或待人工。 |

## Release Gate 判定

| Gate | 判定 | 依据 |
| --- | --- | --- |
| 当前代码确定性回归 | 通过 | 本次当前 HEAD 退出码 0，结果见上表。 |
| 代码/fixture 可追溯 | 通过 | manifest、case set 和主要 fixture SHA 已写入事实包。 |
| 远程 CI 与当前 HEAD 一致 | 未通过 | 当前 HEAD 未推送；成功 Actions 对应旧提交。 |
| live model 行为质量 | 未通过/待重跑 | 旧报告 stale 且 24/72；不能合并为当前通过。 |
| Grounding 证据质量 | 未通过 | 旧报告 4 条 `UNAPPROVED_EVIDENCE_SOURCE`。 |
| 浏览器/集成/故障现场 | 未通过/环境阻塞 | 24/30/36/32 条尚未逐条现场执行。 |
| 生产能力 | 未声明 | 没有生产部署、SLA、真实用户、真实支付/仓储/物流/维修证据。 |

## 允许的简历表述

可以写“在本地合成数据上实现并验证了受限 Agent Runtime、RAG 2.0、Proposal/确认/Java 权威写入边界和版本化确定性发布门禁”；可以写具体的 `349 passed`、`478/478`、`52/52`、`17/17`、`11/11`、`14/14`、`6/6`，并标注本机/合成范围。

不能写“当前 main 的 GitHub CI 已绿”“真实模型准确率”“生产 SLA/吞吐/成本”“全部 E2E 或故障恢复通过”“已接入真实支付、仓储、物流、维修”。

本次没有提交或推送。下一次若要把 Release Gate 改为通过，需要：提交这三份事实文档或另一个明确版本、推送当前 HEAD、等待两条 Actions 对应当前 SHA 成功；在可控环境重新运行同一版本的 live model/Grounding、浏览器 E2E、Java/MySQL、故障注入和 durable recovery，并保留每套件的退出码、fixture hash 与报告路径。
