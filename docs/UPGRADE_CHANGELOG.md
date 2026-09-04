# 重大升级变更记录

本文件记录已完成的命名 Build 与公开发布基线。它不是产品待办清单，也不以“已提交”替代测试或真实验收。

## 2026-09-04 — Build 22 CI 与合成回放收口（`f88fee38b2089a0cc433650480ebac6dc3dcba03`）

- 将 v3 live-synthetic 运行器接入质量合同测试，明确 36 条手工 Case 各运行三次；真实模型不可用时保持环境阻塞，不降级为通过。
- 强化 Executor Prompt 的只读 Skill 白名单约束；写 Skill 只能经 Runtime 生成 Proposal 并等待客户确认。
- 固定 MongoDB Java Driver `4.11.5` 并加入 Micrometer API 兼容回归测试；CI 工作流保留 Python、Java、Web、Compose、gitleaks 和 OSV 门禁。
- 复验：FastAPI `346 passed + 7 subtests`、v3 `478/478 + 8/8`、Quality `17/17`、任务编排 `11/11`、RAG `55/55`、Chunk/Metadata `8/8`、Java portal `14/14`、admin `6/6`、Vue/Compose 通过；live-synthetic `108/108`，p95 `1438 ms`。
- 远程 Actions：`mall-ci` [33841952626](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/33841952626)、`quality-evaluation` [33841952630](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/33841952630)，均真实 success。
- 边界：浏览器 E2E 24 条和 Java/MySQL 30 条 manifest 场景仍未逐条现场验收；本机合成结果不代表生产准确率、SLA、吞吐或外部履约接入。

## 后续归档规则

每次重大升级完成后，主线必须同时完成：

1. 用清晰、可检索的 Git 提交归档，例如 `build-22: ...`；不把未验收的大改动伪装为完成。
2. 在本文件追加一条记录：日期、目标、实际改动、已运行的验证、已知边界和回退依据。
3. 对 FastAPI、Java、Vue、Compose、跨服务或模型行为的变更，按影响范围补充自动化与本机验收证据；未运行项必须明确写出。
4. 推送到公开仓库前执行敏感信息检查；绝不提交 `.env`、密码、API Key、Token、日志、Docker 卷、模型权重、Chroma 索引、真实订单或客户数据。

Git 提交是代码版本锚点；本文件是面向人阅读的变更备注；详细命令与结果放在 [测试与演示证据](TEST_AND_DEMO_EVIDENCE.md) 或对应 Build 文档中。

## 2026-09-03 — Mall v3.0 发布硬化与可回放门禁

- 新增版本化 `evals/v3/release-manifest.json`（478 条 deterministic、36 条 live synthetic、12 个性能 Profile）及 hash/预算/安全字段校验。
- 新增无模型的 `run_v3_release_preflight.py`，对完整注册清单和代表性 Runtime 安全分支执行确定性检查；新增 manifest/evaluation 回归测试。
- CI 在 FastAPI compile/collect 后执行 manifest/preflight；质量工作流纳入同一合同测试，保留 Java、Web、Compose 与安全扫描门禁。
- README、AGENTS、UPSTREAM 与公开证据文档明确 v3 Runtime 的 Agent/Skill/Java 权威边界和本机合成验证口径。
- 当前未宣称：36 条 live 三轮、完整浏览器 E2E、真实外部履约和生产 SLA。远程 Actions 已在公开发布验证基线通过；其结果仅代表当前 CI 门禁，不代表生产部署或生产 SLA。

## 2026-09-02 — 统一售后 Agent 任务感知编排一次性升级

- 目标：让每条新消息先经过受限任务感知 P0，再决定继续当前任务、临时切题、恢复唯一暂停任务、放弃或开始新任务；移除旧 pending 优先抢占。
- 实际改动：新增 `active_task`、最多一个 `paused_task` 与独立 `transaction_gate`；缺订单号改为普通等待输入任务，不再默认创建 LangGraph `interrupt()`；Proposal/Action 不再阻断无关聊天、政策查询或新任务；任务摘要只保存安全字段并绑定会话/身份。
- Agent 边界：P0 只输出闭集 `TurnPlan`；只读调查仍由受控统一售后图执行；Java 继续负责事实、归属、资格、状态机、幂等、事务和最终写入；浏览器仅看到“进行中/已暂存任务”摘要，不看到 task/checkpoint 标识或内部载荷。
- 验证：FastAPI 全量 **317 passed，7 subtests passed**（1 条第三方弃用警告）；Vue 生产构建通过；Java portal 定向 **22/22**、admin 定向 **14/14**；任务编排 `contract_mock` **11/11**、手动真实模型合成评测 **10/10**（总 **23.1 s**、p95 **4.0 s**）；Compose 配置通过；Docker 重建后八个常驻服务健康；网页代理完成缺标识诊断 → 政策临时切题 → AI 服务重启 → 同会话自然恢复，公开响应无内部字段泄露。
- 边界：本次现场使用本机合成会话和现有命名卷，不代表生产 SLA、模型通用准确率或远程 CI；未删除演示数据、数据库卷或历史日志。回退依赖本次前快照 `snapshots/task-orchestration-one-shot-20260902-1815` 与数据库备份。

## 2026-09-01 — 公开发布基线

- 范围：将本地可信 AI 售后与 AgentOps 项目整理为可复现的公开发布包。
- 公开准备：补齐 Apache-2.0 许可入口、上游归属、秘密忽略规则、无本地模型/索引的 Docker 构建、首次 RAG 自举和本地演示身份初始化说明。
- 安全：移除旧 Postman 静态认证值，并重建不含旧值的公开可达 Git 历史；客户数据、账号密码、Token、模型权重、Chroma 索引与 Docker 数据均未纳入发布。
- 验证与边界：见 [公开发布记录](PUBLIC_RELEASE_RECORD.md)；本机测试和 Docker 演示不等于生产上线或模型通用准确率。
