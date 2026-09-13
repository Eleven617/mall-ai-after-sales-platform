# Mall AI 售后平台

[![mall-ci](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/workflows/ci.yml)
[![quality-evaluation](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/workflows/quality-evaluation.yml/badge.svg?branch=main)](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/workflows/quality-evaluation.yml)

一个面向电商售后的可信 Agent Runtime：用户用自然语言提出目标，系统调查订单、物流、库存和政策事实，比较候选处理方案，在明确确认后由 Java 业务层完成最终校验和写入。

本项目基于 Apache-2.0 的 [`macrozheng/mall`](UPSTREAM.md) 二次开发，公开数据、账号、评测和截图均为合成或脱敏数据。它是可本地运行的工程作品集，不是生产 SaaS。

## 30 秒了解项目

> 当前展示状态：`NOT_COMPLETE`。上一轮素材停在确认前，不能证明当前提交已经完成 Java 写入与状态回查；本轮尝试受真实 DeepSeek Provider HTTP 402（余额不足）阻断，未使用 mock 冒充。三条素材需在额度恢复后通过 [`scripts/Capture-PublicShowcase.ps1`](scripts/Capture-PublicShowcase.ps1) 重新录制并逐帧复核。

### 为什么不是普通聊天机器人

LLM 只在受限 Schema 内理解目标、选择已注册 Skill、规划只读调查并生成草案。订单、物流、资格和售后状态由 Java 提供；JWT/归属、资格、状态机、幂等、事务、Outbox 与最终写入也由 Java `mall2/` 负责。没有用户确认和 Java 重校验，模型不能写业务库，浏览器也不能绕过服务端写接口。

核心数据流：

```mermaid
flowchart LR
  U[客户目标] --> R[FastAPI Agent Runtime]
  R --> S[Skill 白名单与 Context]
  S --> F[Java 订单/物流/资格事实]
  S --> G[版本化政策 RAG]
  F --> P[事实卡与候选方案]
  G --> P
  P --> C[用户明确确认]
  C --> V[Java 重校验]
  V --> T[MySQL 事务与幂等]
  T --> O[Outbox / RabbitMQ]
  R --> W[Vue 安全公开 DTO]
```

### 一个核心 Agent，两个辅助 AI 能力

| 能力 | 面向角色 | 主要输入/输出 | 写入边界 |
| --- | --- | --- | --- |
| 统一售后开放任务 Agent | 客户 | 自然语言目标 → 事实卡、政策证据、候选方案、确认卡 | Java 确认后重校验并写入 |
| 运营分析 AI | 运营人员 | Java 可信聚合 → 受限分析草稿 | 只读 |
| AI 质量评测 | 开发/质量人员 | 版本化合成 EvalCase → 硬规则结果与失败摘要 | 不读取生产数据，不自动改代码 |

MCP 只读工具、人工售后工作台和 LangGraph 确定性节点是能力边界或执行设施，不是额外的在线 Agent。

## 三条展示链路（当前复核状态）

计划中的三条真实链路是：

1. 开放目标 → 多步事实/政策调查 → 候选 → 用户确认 → Java 重校验/写入 → 状态回查；
2. 等待输入 → 暂停保留 → 政策岔开 → 同一任务恢复；
3. 事实版本变化 → 旧结果失效 → 重新核验 → 新方案或人工交接。

当前提交尚未重新生成这三条完整 GIF。旧 PNG/GIF 仅作为历史素材保留，不能在本 README 中被称为当前闭环证据。实际素材、阻断原因和逐帧验收记录见 [展示素材证据](docs/evidence/final-showcase-evidence.md)。

## 架构与代码入口

- `mall-ai-service/app/runtime/`：Task Runtime、计划、Skill/Tool 白名单、Context 投影、Proposal 和安全停止。
- `mall-ai-service/app/services/`：统一售后、RAG、MCP、任务记忆、Trace/Eval 与角色化 API。
- `mall2/mall-portal/`、`mall2/mall-admin/`：Java 事实、权限、资格、状态、幂等、事务、Outbox 和人工协同。
- `mall-ai-web/src/`：客户、运营、质量和人工处理人员的 Vue 页面，只消费公开 DTO。
- `evals/` 与 `mall-ai-service/scripts/`：版本化 EvalCase、RAG/grounding、v3 manifest、现场和发布门禁。

政策 RAG 是证据层，订单事实仍走 Java。Dense 是当前默认检索；Hybrid 和 Hybrid+Rerank 保留为可复现实验。

## 当前评测结论

结果按套件独立统计，不相加，也不外推为生产 SLA 或真实用户泛化：

- 当前提交 FastAPI：`366 passed`；Java portal 核心 `12/12`、兼容性 `2/2`、admin `6/6`、Spring context `1/1`；
- 历史补充评测集（supplemental evaluation set）参与过开发期回归，不是独立盲测集；其旧 `36/36` 结果已因 Runtime 提交变化标为 stale；
- RAG：Dense、Hybrid、Hybrid+Rerank 分别在 52 条版本化合成政策 Case 上评测；Dense 当前 MRR `0.948718`、nDCG@3 `0.962147`，作为默认方案；这些是检索指标，不是答案准确率；
- deterministic 合同：`478/478`，代表性 Runtime `8/8`，不是 E2E；
- Vue production build 通过；当前代码提交的 DeepSeek 现场展示为 `environment_blocked`（Provider HTTP 402），不能把旧提交的 `72/72`、`36/36`、`122/122` 当作当前结果。

历史失败、根因和修复过程见 [evaluation-evolution](docs/evidence/evaluation-evolution.md) 与 [failure matrix](docs/evidence/final-agent-failure-matrix.md)。当前数字的唯一事实源是 [`current-release-facts.json`](docs/evidence/current-release-facts.json)，并由 [`validate_public_release.py`](scripts/validate_public_release.py) 在 CI 中校验。

## 本地运行

前置条件：Docker Desktop 已启动。完整模型演示需要运行者自己的 DeepSeek Key；不配置 Key 也可以运行结构、权限和 deterministic 合同。

```powershell
git clone https://github.com/Eleven617/mall-ai-after-sales-platform.git
Set-Location .\mall-ai-after-sales-platform
.\scripts\Prepare-PublicDemo.ps1
```

只运行无模型合同：

```powershell
.\scripts\Prepare-PublicDemo.ps1 -SkipLiveModel
```

启动后：<http://127.0.0.1:5173>、<http://127.0.0.1:8000/docs>、<http://127.0.0.1:8085>。

```powershell
.\scripts\Initialize-LocalDemoAccess.ps1 -PrepareCustomerFixtures
```

本地账号由运行者自行初始化，密码不会写入仓库。

## 当前验证范围

验证使用本地 Docker/Chrome/Java/MySQL/Redis/RabbitMQ 和合成 Fixture。仓库不接入真实支付、仓储、物流或维修履约，不宣称生产 SLA、用户量、QPS、成本下降或真实用户准确率。价格未配置，因此不能从模型 Token 推导真实费用。

## 上游归属与贡献边界

`mall2/` 的商城订单、会员和后台基础能力来自 `macrozheng/mall` 上游；本项目新增的是 AI 售后入口、受控 Task Runtime、统一售后编排、RAG/证据核验、Skill/Tool、Trace/Eval、MCP 只读边界、Java AI 接口、人工案件和角色化 Vue 工作台。详细边界见 [UPSTREAM.md](UPSTREAM.md)、[贡献矩阵](docs/CONTRIBUTION_MATRIX.md) 与 [NOTICE](NOTICE)。

## 进一步阅读

- [架构与责任边界](docs/architecture.md)
- [展示素材证据](docs/evidence/final-showcase-evidence.md)
- [测试与演示证据](docs/TEST_AND_DEMO_EVIDENCE.md)
- [公开发布记录](docs/PUBLIC_RELEASE_RECORD.md)
- [评测、Profile 与安全回放](docs/evaluation.md)
- [贡献与本地验证](CONTRIBUTING.md)
- [安全问题](SECURITY.md)
- [工程协作规则](AGENTS.md)
