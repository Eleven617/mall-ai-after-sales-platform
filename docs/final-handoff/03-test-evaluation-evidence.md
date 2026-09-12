# 测试、评测与现场证据

## 当前权威快照｜最终公开收口（2026-09-12 UTC）

运行时代码：`9c7c29045c28446b16a609768cd4b4c1202f8a51`。FastAPI **365 passed**；DeepSeek main **72/72**、supplemental **36/36**（非独立盲测）；Grounding **15/15、57/57 checks**；deterministic **478/478、8/8**；Java portal core **12/12** + compatibility **2/2**、admin **6/6**、Spring **1/1**；Vue production build passed；本地现场 **122/122**。所有套件按本机/合成/远程 CI 分开统计，不能相加为生产准确率。

原始报告路径、退出码和 hash 见 [`current-release-facts.json`](../evidence/current-release-facts.json)；现场报告的 Fixture SHA 为 `4dd3d407001aec74e4c9546639c78eb2544b34a0ac4f2b6698eba345c27e3fc3`。最终证据提交 `78c5c3c` 的两个远程门禁已 success；运行时代码仍绑定 `9c7c290`。

## 历史审计记录（以下内容不代表当前 Commit）

## 2026-09-12 当前代码补测

当前运行时代码：`52d5482455e2389cfd6c2ef15d233712607ffa9f`。FastAPI **362 passed**；live model main **72/72**、holdout **36/36**；Grounding **15/15、57/57 checks**；v3 deterministic **478/478、8/8**；Java portal/admin **12/12、6/6**；Vue build 通过；本地四类现场 Runner **122/122**。原始报告和 hash 见 [`final-agent-quality-baseline.md`](../evidence/final-agent-quality-baseline.md)。旧数字如与本节冲突，按 stale/superseded 处理。

## 证据原则

每个结果都绑定命令、退出码、运行模式、Commit、Fixture/报告 hash 和限制。确定性合同、真实 Docker 现场、合成模型评测和远程 GitHub CI 分开统计，不能相加。

## 最新现场报告

| 字段 | 值 |
| --- | --- |
| 报告 | `tmp/field-acceptance/field-20260909T105750Z-12222b15/field-acceptance.json` |
| 报告 SHA-256 | `6a301cd28072ebbf01fa07e81d7aaf5c4b2de9741c14ceb351122cac18f21567` |
| Fixture SHA-256 | `7573e19271528e904d2eb40cef2765f05d4e5f489f2b35cc1b1359bcd5128759` |
| 运行时代码 | `84e111d17e4117287660421ea5772a9ddcf44382` |
| Docker | Engine `29.7.2`；Compose 配置有效；主/隔离项目健康 |
| 结果 | 122 executed，122 passed，0 failed，0 environment_blocked |
| 总时长 | 211947 ms |

## 确定性与本机回归

| 套件 | 命令/模式 | 结果 | 能证明什么 |
| --- | --- | --- | --- |
| FastAPI | `mall-ai-service/.venv/Scripts/python.exe -m pytest -q` | 353 passed，7 子断言，1 warning，exit 0 | 当前 Python 合同/回归 |
| Runner 合同 | `pytest` 受影响 Runner 测试 | 11 passed，exit 0 | runner schema/断言完整性 |
| v3 manifest | `validate_v3_release_manifest.py --json` | 478/478 | 注册合同与白名单完整 |
| v3 preflight | `run_v3_release_preflight.py --json` | 8/8 | 确定性依赖前置 |
| quality-agent | `run_quality_agent_evaluation.py` | 17/17 | 质量 Agent 合同 |
| task orchestration | `evaluate_task_orchestration.py --mode contract_mock` | 11/11 | 任务感知/状态合同 |
| RAG verifier | `evaluate_rag_verifier.py` | 36/36（28 支持、8 无证据） | 证据支持/拒答硬规则 |
| chunk metadata | `evaluate_chunk_metadata.py --summary` | 8/8 | Chunk 契约/元数据 |
| Java portal | Maven，`-DskipTests=false` 定向套件 | 14/14 | Portal 业务/Outbox 相关单测 |
| Java admin | Maven，`-DskipTests=false` 定向套件 | 6/6 | 运营/案件相关单测 |
| Spring/MySQL | `MallPortalApplicationTests` + 临时 Compose 连接配置 | 1/1 | 本机 Java context 与 MySQL 连接 |
| Vue | `npm run build` | exit 0 | 前端生产构建 |
| Compose | `docker compose config --quiet` | exit 0 | 配置语法 |

## RAG 与模型评测

- 52 条版本化黄金集：Dense Recall@1 `1.0`、MRR `0.948718`、nDCG `0.962147`；Hybrid 为 `0.935897/0.952683`，Rerank 结果相近但延迟/复杂度更高，因此 Dense 保持默认。
- Grounding 合成评测：15 cases，11 passed、4 quality_failed（`UNAPPROVED_EVIDENCE_SOURCE`）；这不是生产准确率。
- live_model_synthetic 开放任务：24 passed、48 failed、0 blocked（每 case 多次运行）；只用于暴露模型/编排问题，不能推断自然语言泛化。
- 真实模型调用没有作为默认 CI 门禁；无 Key 或 Provider 不可用时应标记 `environment_blocked`，不能用 mock 数字替代真实效果。

## Build 14A

`tmp/run_build14.ps1` 调用 `verify_build14_eligibility_live.py`，最新退出码 `0`。负路径确认 Java 拒绝未收货订单，正路径经过运营发货与客户确认收货后创建申请；第二账号不可见、同幂等键不重复创建、事务 Outbox 存在。该验证使用真实 API 和本地合成数据，不直接改数据库。

## 远程 CI

当前基线 `5ea1199` 的 `mall-ci` 与 `quality-evaluation` 已真实 success；本次交接提交推送后必须再次确认与最终 SHA 对齐。CI 通过只证明工作流在 GitHub runner 上通过，不代表生产部署。

## 历史与限制

旧 Fixture 产生的阻断报告是 superseded；旧 Commit 的现场结果是 stale。历史 Build 21 曾出现等待任务缺失的独立重跑失败，已保留为运行时波动，不被隐藏。没有真实支付/仓储/物流/维修系统、生产告警、生产 SLA 或真实客户数据。
