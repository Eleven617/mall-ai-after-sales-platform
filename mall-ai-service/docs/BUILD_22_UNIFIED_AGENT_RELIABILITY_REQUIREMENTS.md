# Build 22：统一售后 Agent 最终收口——受控 ReAct、可恢复执行与可靠性闭环

> 状态（2026-08-25）：Build 22 已完成实现、单元回归、Vue 生产构建和 Docker 本机验证。已验证的范围与仍未重跑的人工页面操作在第 7、8 节分别记录；这不是生产上线或生产 SLA 的声明。

## 1. 目标与产品命名

用户侧产品统一称为 **统一售后 Agent**。订单/物流异常排查是其中的受控、只读调查子流程，
不是另一个客户产品或第四个 Agent。

本 Build 只收口三项已有能力：

1. 将现有 Build 14 多工具诊断图作为统一售后 LangGraph 内的受控只读调查子流程接入；
2. 记录已完成的 Build 21 登录双账号暂停、重启、恢复和拒绝现场验收；
3. 为既有三个角色补齐隐私安全 Trace、轨迹评测、红队回归与 CI 门禁。

三个既有角色不变：统一售后 Agent、运营分析 Agent、AI 质量评测 Agent。

## 2. 实现结果与保留决定

- `unified_after_sales_graph.py` 保持政策、资格、申请、列表、状态、取消、修改、跟进八类固定
  动作，并将既有多工具诊断收口为 `read_only_investigation` 子流程；写操作仍不进入 ReAct。
- `diagnosis_agent.py` 保持最大步数、工具白名单、重复调用限制、Java 归属校验和 RAG 证据
  门槛，并补齐可注入的评测起点和 `tool_failure` 安全 Trace 结果。
- `durable_diagnosis.py` 的缺标识暂停继续只保存脱敏、owner-bound Redis checkpoint；完整
  DiagnosisState、客户原话、订单号、Token、RAG 原文和工具原始结果均不持久化。
- `trace_service.py` 已统一为 `trace-v2` 白名单 schema，支持内存捕获与 sink 故障吞掉；只允许
  流程、节点、工具名、时长、结果种类、诊断类别、证据状态、handoff 和合同违反等元数据。
- `quality_evaluation_agent.py` 已将第三个质量 Agent 扩展为 17 条 `contract_mock` 轨迹/红队
  回放，以及 3 条手动 `live_model_synthetic` 真实模型合成回放；两者都不读取生产数据或写业务。
- `operations_agent.py` 仅补充安全生命周期 Trace，继续只读人工选择的 7/30 天 Java 聚合，不加
  ReAct，也不扩大运营数据范围。

## 3. 受控 ReAct 设计

```text
受限 Intent 模型选择 route=agent
-> 统一售后 LangGraph 的 read_only_investigation 节点
-> 既有诊断 StateGraph：decide -> approved read-only tool -> verified facts -> decide
-> 完成 / 安全暂停 / 安全交接
-> 客户只接收事实卡、证据状态和允许下一步
```

- 仅 `route=agent` 且服务端闭集允许的订单/物流异常诊断进入该子流程；政策、资格、申请、
  列表、状态、取消、修改、跟进不自由化。
- 模型仅能在 `order_service`、`logistics_service`、`inventory_service`、`rag_search` 中提议
  下一步；每次提议仍经过 JSON Schema、工具白名单、参数校验、当前用户 Java 事实边界、最大
  步数和时间预算。
- 订单、物流、资格和政策结论由 Java/RAG verified facts/evidence package 决定；模型文本不
  能覆盖事实。创建、取消、修改继续只能走 pending proposal/action -> 明确确认 -> Java。

## 4. 数据可见性与不变量

| 不变量 | 必须保持 |
| --- | --- |
| 客户公开响应 | 不含 intent、Prompt、Token、完整订单号、RAG 原文/chunk/分数、工具原始结果、Outbox、Trace、checkpoint 或内部 ID。 |
| Redis checkpoint | 仅存版本、流程、owner fingerprint、等待字段、允许工具、状态、TTL/恢复计数；不存原话、标识、Token、RAG 或工具载荷。 |
| Trace | 仅存版本化白名单元数据：flow/node/tool_name/duration/result_kind/diagnosis_category/evidence_status/handoff/contract_violation 等；未知字段一律丢弃。 |
| 质量评测 | 只读版本化合成输入、模拟工具/指标；不连生产数据库、真实聊天、真实 CaseHandoff、生产 Trace 或业务写接口。 |
| 运营分析 | 仍只读 Java 聚合、人工固定 7/30 天窗口、一次受限结构化草稿；不加 ReAct。 |
| 观测与评测失败 | 不能阻塞客户请求，不能改变 Java 写入、Outbox 或售后结果。 |

## 5. 实际文件范围

| 区域 | 预计文件 | 目的 |
| --- | --- | --- |
| 统一售后 ReAct 收口 | `app/services/unified_after_sales_graph.py`、`app/services/diagnosis_agent.py` | 将现有只读诊断图放入统一售后图，保留有界工具调用、安全停止与事实门槛。 |
| 可恢复执行 | `app/services/durable_diagnosis.py`、`scripts/verify_build21_authenticated_live.py` | 保持脱敏、owner-bound checkpoint，并保留 A/B 重启/拒绝网站代理验收。 |
| 安全 Trace | `app/services/trace_service.py`、`app/services/operations_agent.py` | 落地 `trace-v2` allow-list、时长/结果种类/合同违反字段和非阻塞 sink。 |
| 轨迹/红队评测 | `app/schemas/quality.py`、`app/services/quality_evaluation_agent.py`、`evals/quality_agent_cases.v2.json`、`evals/live_model_synthetic_cases.v1.json` | 对工具顺序、步数、停止、拒绝和无写入做确定性比较；真实模型档只使用合成夹具。 |
| 开发者质量页与 CI | `app/routers/quality.py`、`mall-ai-web/src/api.ts`、`mall-ai-web/src/types.ts`、`mall-ai-web/src/QualityPanel.vue`、`repository-root/.github/workflows/quality-evaluation.yml` | 页面显式区分 CI 默认的 `contract_mock` 与手动的 `live_model_synthetic`；CI 只跑前者。 |
| 测试与记录 | `tests/test_trace_service.py`、`tests/test_quality_evaluation_agent.py`、`tests/test_unified_after_sales_graph.py`、`tests/test_durable_diagnosis.py`、本文件与主计划文档 | 回归不变量、记录已验证证据和未验证边界。 |

不预期修改 Java 业务 API、数据库表或真实支付/仓储/物流/维修适配器；若实施时发现无法保持既有
Java 契约，会先停止并报告，而不是静默扩大范围。

## 6. 评测档位与成本/延迟

| 档位 | 触发 | 数据与模型 | 裁决 |
| --- | --- | --- | --- |
| `contract_mock` | 每次 CI/PR | 合成案例、模拟工具、无真实模型 | 确定性比较器，失败阻止合并。 |
| `live_model_synthetic` | 手动、夜间、模型/Prompt/Tool Schema/RAG/LangGraph 变更后或发版前 | 真实模型 + 真实编排，但只有版本化合成输入与模拟工具 | 确定性硬规则；模型只接受被测，不是裁判。 |
| LLM 失败归因 | 仅确定性失败后、开发者显式选择 | 脱敏 expected/actual/violation 摘要 | 只提供建议，永不把失败改为通过或自动修改任何资产。 |

固定售后路径不新增 LLM 调用。只读调查沿用已有有界 ReAct 预算；Build 21 恢复继续不额外调用
模型。`live_model_synthetic` 不进入客户链路，因此其网络/成本/超时不会阻塞客户。

## 7. 验收矩阵与实际证据

| 编号 | 场景 | 预期证据 |
| --- | --- | --- |
| B21-L1 | A 登录，缺订单号 -> interrupt -> 重启 AI 服务 -> 同会话补订单号 | `verify_build21_authenticated_live.py` 的登录 A 网站代理路径已通过；只读事实卡返回且无业务写入。 |
| B21-L2 | B 使用 A 的会话/恢复输入 | 同一现场脚本已验证 B 在 owner 校验处被拒绝，未返回 A 的事实。 |
| B21-L3 | 过期、取消、Redis 不可用、版本不兼容、重复/并发 resume | `tests/test_durable_diagnosis.py` 覆盖并通过；安全停止且无重复读写。 |
| B22-R1 | 多工具订单异常 | `contract_mock` 17/17 通过，覆盖批准工具顺序、步数预算和重复调用阻断。 |
| B22-R2 | 无证据、工具故障、非法工具/参数、模型不可用 | 同一确定性套件通过；模型无效或工具失败不会进入写操作。 |
| B22-R3 | prompt injection、恶意工具结果、跨账号订单、伪造标识、恢复重放、近似政策 | 红队夹具由确定性边界拒绝；预期拒绝被识别为 PASSED，回归时将令 CI 失败。 |
| B22-O1 | 运营合成案例 | 17 条套件包含窗口、可信聚合数字和写入声明合同；运营模型真实档也通过 1 条合成案例。 |
| B22-Q1 | 质量 Agent 合成运行 | 本机和 Docker 均为 `contract_mock` 17/17；Docker `live_model_synthetic` 3/3，`environment_blocked=False`。 |
| B22-V1 | Vue、Docker、三角色演示 | Vue 生产构建通过，Compose 七项服务 healthy，`/quality` 返回 200，未登录重跑接口返回 401。此前登录客户统一售后/B21 A-B 网站代理已通过；本轮未重新做运营和开发者登录后的人工点击录屏。 |

本轮最终回归：Python 全量 `221 passed, 20 subtests passed`；Build 22 相关定向测试
`38 passed`；Vue `npm run build` 通过。`contract_mock` 未调用模型，`live_model_synthetic`
只使用版本化合成输入、模拟工具和模拟聚合指标，且最终 3/3 通过。

## 8. 非目标与真实边界

- 不新增第四个在线 Agent、swarm、MCP、通用 Skill Loader、长期记忆或 Build 23 功能。
- 不为名词改变 Dense 默认，Hybrid/Rerank 仍以 Build 20 测量结论为准。
- 不接入不存在的外部履约系统，也不把本机、小样本或模型评测描述成生产准确率/SLA。
- 仍不宣称已验证跨进程崩溃中工具严格一次、生产吞吐、高可用、真实外部回调大规模重放。
- 未在本轮重新执行“登录运营人员打开页面”和“登录开发者在浏览器点击重跑”的手工录屏；已有
  角色 API/隔离自动化和质量页面静态/未登录拒绝验证不能替代该演示证据。
- GitHub Actions 工作流已配置为只跑 `contract_mock`，但本机执行的等价命令不等同于一次已观察到的
  托管 CI 运行；远端仓库触发记录仍应在交付阶段单独保留。
