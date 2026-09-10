# GitHub 展示升级与验证证据

生成日期：2026-09-10（Asia/Shanghai）  
仓库：`https://github.com/Eleven617/mall-ai-after-sales-platform`  
分支：`main`  
展示实现提交：`207901b6f24700da37525c6b8843238af4a19d25`（`docs: refresh GitHub showcase`）

本次只更新公开展示文档、架构说明和真实页面截图；没有修改业务代码、测试断言、依赖、迁移或 Compose 正式配置。展示提交的业务代码仍沿用此前已验证的实现。后续证据文档提交为展示提交的 docs-only 后继，不改变运行时代码；最终交接时仍以 `git rev-parse HEAD` 和本文件记录的测试提交为准。

## 1. 本次公开展示内容

### README 与架构

- `README.md` 顶部改为“一个核心 Agent + 两个辅助 AI 能力”：统一售后开放任务 Agent、运营分析 AI、AI 质量评测。
- 明确 MCP 只读工具、人工工作台和 LangGraph 确定性节点不是额外的在线 Agent。
- 增加“不是普通聊天机器人”的 Java 权威写入边界、事实/知识分离、ActionProposal/确认门和四层闭环。
- 增加能力矩阵、开放任务案例、真实验证口径、Quick Start、上游二次开发边界和非生产声明。
- `docs/architecture.md` 改成交互层、Agent Runtime 层、证据与工具层、可信执行层四层图，并列出主要真实代码位置。

### 截图与 GIF

所有图片都由本地 Docker Compose 页面、真实 Chrome/CDP 和合成账号/订单生成；没有使用 ImageGen、假 UI 或真实客户数据。Agent/运营截图使用了只在本机进程内运行的一次性 OpenAI-compatible 合成展示 Provider，以便稳定产生事实卡和候选草案。这是展示夹具，不是模型准确率测试，也不会写入业务数据。

| 文件 | 尺寸 | SHA-256 | 内容 |
| --- | --- | --- | --- |
| `docs/assets/customer-open-task.png` | 1440×1000 | `ad12849eabfb8e3ba8edce51f5659e33bbbfc792f8c51b8e93938edb7812fa3c` | 客户开放任务页 |
| `docs/assets/agent-investigation-workspace.png` | 1440×1400 | `85f233c36e112174d93fea5699c33bd1f43d578193b63a6d2fdfa3fdc5fb0154` | Java 事实、政策证据、候选草案和等待确认卡 |
| `docs/assets/operations-analysis-result.png` | 1440×1100 | `5159708b6d18e166ad7f754486c69638c43e30a9635ec74226bb853163af4944` | 运营可信聚合与分析草稿 |
| `docs/assets/quality-evaluation-summary.png` | 1440×1000 | `1ada0f4374fa0531169bf75b9f914402655482a68897830a030ced709be9447b` | quality-agent.v2 `17/17` 摘要 |
| `docs/assets/open-task-demo.gif` | 960×900，4 帧，12 秒 | `7a692744e1e1bfe31f2efe9e35a192886309d45c125bb5a943063ee89a1e41d2` | 真实页面的轻量流程剪辑 |
| `docs/assets/social-preview.png` | 1280×640 | `baf0590a1a40130d9acb32ca9913df15c1366d6819a8efd6f0a5915eff41d206` | GitHub Social preview 视觉图 |

仓库中原有的四个兼容截图文件也被同一批真实页面重新生成并随展示提交保留：`agent-task-workspace.png`、`customer-policy-conversation.png`、`operations-handoff-overview.png`、`quality-evaluation-dashboard.png`。

## 2. 合成开放任务场景

本次展示使用一次性合成客户和合成订单。自然语言目标是“核验订单、物流、库存和政策依据，比较补发、换货和退款方案，并在我确认后提交”。展示 Provider 先后提出已注册的只读调查：物流、库存、政策证据；Runtime 将它们投影为安全 Artifact，再生成候选 ActionProposal。

页面最终显示“等待确认”和候选方案。没有点击确认，没有向 Java 写接口提交售后申请，也没有伪造退款、仓储、物流或维修完成。公开页面没有显示完整订单号、Token、内部 Trace、原始工具载荷或 RAG 原文。

这条路径证明的是：本地页面可运行、公开 DTO 边界正确、只读事实到 Proposal 的展示链路可复核。它不能证明真实 Provider 的自然语言泛化、生产吞吐或外部履约成功。

## 3. 本轮实际执行命令与结果

以下命令均在 `C:\Users\12969\Desktop\mall` 工作区执行；密码只在进程环境中短暂存在，报告不记录其值。

| 检查 | 命令/动作 | 退出码与结果 |
| --- | --- | --- |
| Compose 配置 | `docker compose config --quiet` | `0` |
| Compose 现场 | `docker compose ps` | 8 个常驻服务均 `running/healthy`；未执行 `docker compose down`、删卷或清库 |
| FastAPI 回归 | `Push-Location mall-ai-service; .\\.venv\\Scripts\\python.exe -m pytest -q; Pop-Location` | `0`；`353 passed`，1 条第三方弃用警告，7 个参数化子断言 |
| Vue 构建 | `Push-Location mall-ai-web; npm run build; Pop-Location` | `0`；`vue-tsc --noEmit` 与 Vite production build 通过 |
| Java portal | `mvn -pl mall-portal -am "-Dtest=AiCaseHandoffServiceImplTest,AiServiceCaseServiceImplTest,AiServiceCaseOutboxPublisherTest,AiServiceCaseEventReceiverTest,SpringDataWebExposureContractTest,MongoMicrometerCompatibilityTest" "-DskipTests=false" "-Dsurefire.failIfNoSpecifiedTests=false" test` | `0`；`14/14`，失败/跳过 `0` |
| Java admin | `mvn -pl mall-admin -am "-Dtest=AiServiceOperationsServiceImplTest,AiServiceOperationsControllerTest" "-DskipTests=false" "-Dsurefire.failIfNoSpecifiedTests=false" test` | `0`；`6/6`，失败/跳过 `0` |
| v3 清单 | `mall-ai-service/.venv/Scripts/python.exe scripts/validate_v3_release_manifest.py --json` | `0`；deterministic `478`，live case 注册 `36`，性能 Profile `12`，hash 校验通过 |
| v3 预检 | `mall-ai-service/.venv/Scripts/python.exe scripts/run_v3_release_preflight.py --json` | `0`；`478/478` deterministic，代表性 Runtime `8/8` |
| 质量合同 | `mall-ai-service/.venv/Scripts/python.exe scripts/run_quality_agent_evaluation.py` | `0`；`quality-agent.v2` `17/17` |
| Chunk/Metadata | `mall-ai-service/.venv/Scripts/python.exe scripts/evaluate_chunk_metadata.py --summary` | `0`；`8/8`，合成 chunk `5`，外部模型调用 `0` |
| RAG 2.0 | `mall-ai-service/.venv/Scripts/python.exe scripts/evaluate_rag2.py --summary` | `0`；Dense/Hybrid/Hybrid+Rerank 各 `52/52`；Dense MRR `0.948718`、nDCG@3 `0.962147`；Rerank p95 本轮 `1909.93ms` |
| 浏览器截图 | 被 Git 忽略的 `tmp/capture_demo_screenshots.py`、`tmp/capture_stub_showcase.py`、`tmp/capture_operations_quality_showcase.py`、`tmp/capture_social_preview.py`，使用真实 Chrome/CDP；密码通过运行期环境变量提供 | 各脚本退出 `0`；PNG/GIF 尺寸与 hash 如上 |
| 公开元数据核对 | GitHub REST API 读取仓库信息 | Description、11 个 Topics、默认分支 `main`、仓库 `public` |
| 差异检查 | `git diff --check` | `0` |

本轮测试计数独立报告，不能相加。RAG 的 52 条是版本化小型合成政策集；deterministic 478/478 是无真实模型、无业务写入的合同门，不是 478 条真实用户任务。

## 4. Docker、现场与历史证据的分层

最新已有现场报告记录了本地合成 Docker/Chrome/Java/MySQL/Redis/RabbitMQ Runner：browser `24/24`、Java/MySQL `30/30`、fault `36/36`、durable recovery `32/32`，报告位于被 Git 忽略的 `tmp/field-acceptance/field-20260909T105750Z-12222b15/field-acceptance.json`，SHA-256 为 `6a301cd28072ebbf01fa07e81d7aaf5c4b2de9741c14ceb351122cac18f21567`；Fixture SHA-256 为 `7573e19271528e904d2eb40cef2765f05d4e5f489f2b35cc1b1359bcd5128759`。该报告的运行时代码提交是 `84e111d17e4117287660421ea5772a9ddcf44382`，展示提交只改文档和资产，因此不能扩写成生产能力或真实用户泛化。

旧的 live-model/Grounding 报告如果提交号与当前 HEAD 不一致，必须标记为 stale；它们不与本轮 deterministic、截图或现场数字合并。历史真实模型样本不能写成通用准确率、成本或 SLA。

## 5. Git 与远程 Actions

展示实现提交已经推送到 `main`：

- `207901b6f24700da37525c6b8843238af4a19d25` — `docs: refresh GitHub showcase`
- [`mall-ci` run 34467222374](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34467222374) — **success**
- [`quality-evaluation` run 34467222378](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34467222378) — **success**

随后补充开放任务案例和 Bad Case 说明的 docs-only 提交为 `7b9a54d4f901a153a07f5bb2ea61de27e2fe097f`：

- [`mall-ci` run 34468309174](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34468309174) — **success**
- [`quality-evaluation` run 34468309202](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34468309202) — **success**

这些链接分别与对应提交 SHA 一致。当前证据文件本身是其后的 docs-only 提交，不改变业务代码；交接时仍应再用 GitHub Actions 页面核对最新 `main` 运行状态。

## 6. GitHub 网页端仍需手动做的动作

仓库 Description 和 Topics 已存在并已核对，无需再次设置。若希望仓库卡片显示自定义预览图：

1. 打开仓库的 **Settings → General**。
2. 找到 **Social preview**，选择 **Upload an image**。
3. 上传 `docs/assets/social-preview.png`（必须是本文件记录的 1280×640 合成图片）。
4. 保存后回到仓库首页检查预览，不要创建 Release，不要修改仓库可见性。

个人主页 README 已存在于 `Eleven617/Eleven617`；本次没有覆盖个人主页内容，也没有创建额外账号。

## 7. 不能宣称的内容

- 不能把本地截图或 process-only 合成 Provider 说成真实模型准确率。
- 不能把 deterministic `478/478` 说成 478 条现场 E2E 或真实客户任务。
- 不能宣称生产 SLA、QPS、成本下降、用户量、线上告警或真实支付/仓储/物流/维修成功。
- 不能把 `macrozheng/mall` 上游商城、订单和会员基础代码说成个人原创。
- 不能把历史 live-model/Grounding 数字当作当前 HEAD 的稳定泛化结果。
