# 评测演进与失败归因记录

## 2026-09-21｜v3.0.4 最小在线复测前行为矩阵

本节绑定的是待冻结的 `agent_runtime_v3_4` 源码状态；最终 Runtime Commit、现场报告和 CI SHA 由 `current-release-facts.json` 在冻结后记录。历史在线 Report、Ledger 与 Lock 保持原样。旧脱敏报告只保存了安全错误类别，没有保存原始模型响应或推理，因此不能反推出缺字段、枚举错误、截断或 JSON 解析中的某一个具体原因。

| Case | 根因与证据边界 | 通用改动 | 预期行为 | 离线回归 |
| --- | --- | --- | --- | --- |
| `agent-open-003` | 历史首轮为 `terminal_status_mismatch` / `required_skill_or_fact_missing`，后两轮通过；具体 Schema 原因无法由现有脱敏证据确定，保留为模型质量不确定性 | `ExecutorDecision` 拒绝跨决策字段；Prompt 显式规定只读事实后 `finish -> completed` | 先 `read_order`，已有核验事实且无限制码时只读完成，不混入 Proposal/澄清字段 | `test_structured_output_gateway.py` 的互斥形状正反例；`test_task_runtime.py` 的读取后完成路径 |
| `agent-open-006` | 历史首轮同上、后两轮通过；无法确定具体 Schema 原因 | 同一模型可见 Schema 与服务端互斥校验；Prompt 明确 `call_skill` 仅推进调查，取得政策和实时事实后才完成 | 政策证据与订单/物流事实分别读取，不能提前结束或把两类事实混写 | 结构化输出专项与 Runtime 多事实路径；Contract Replay 对固定合同执行 |
| `agent-open-010` | 历史首轮同上、后两轮通过；无法确定具体 Schema 原因 | Prompt 明确 `finish/completed` 与 `propose_action/ready_to_commit` 的边界，服务端拒绝互斥载荷 | 只读方案比较取得 `resolution_candidate` 后完成，不形成写 Proposal | Prompt 合同断言、互斥载荷反例、Contract Replay |
| `holdout-open-011` | `live_model_agent_holdout_cases.v2.json` 的 allow-list 漏掉 fixture 中必要的只读 `build_service_resolution`，属于 `evaluation_bug` | v3 overlay 仅补入该合法只读 Skill；过期 Proposal、权限和无写入断言不变 | 合法方案构建不再误报 `irrelevant_skill_call`，过期 Proposal 仍必须拒绝 | v2/v3 语义审计；合法必要调用通过、真正无关调用仍失败的评测测试 |
| `holdout-open-012` | 与 011 相同，属于 `evaluation_bug` | v3 overlay 补入 `build_service_resolution`；重复确认幂等和无重复写入断言不变 | 方案构建合法，重复确认仍至多一次有效写入 | v2/v3 语义审计与 Contract Replay 的重复确认后置检查 |
| `rag2-042` | 历史 `OUTCOME_MISMATCH`；当前政策可回答而旧转述造成模型选择波动，归为 `model_quality_issue` | 回答与证据核验 Prompt 明确当前发布政策优先，旧转述不能覆盖当前规则 | 当前政策直接覆盖限定条件时回答；证据仍不足时拒答 | `test_current_policy_can_answer_despite_user_recalling_an_old_rule` 及政策查询投影测试 |
| `rag2-043` | 历史 `UNAPPROVED_EVIDENCE_SOURCE`；模型加入相邻但不适用来源，归为 `model_quality_issue` | 证据核验要求最小且直接的来源集合；第八天问题只绑定“超过七天售后” | 回答使用适用版本和最小来源，不附带七天内规则 | `test_after_window_answer_uses_only_the_directly_applicable_section`，并保留未知来源拒绝测试 |
| `rag2-045` | 历史 `OUTCOME_MISMATCH`；“原路退款”不能推出到货付款提现，归为 `model_quality_issue` | 查询投影确定性拒绝未覆盖支付路径；回答/核验 Prompt 禁止把退款时效当提现证据 | 提现/转账问题证据不足时拒答；普通退款到账问题仍可回答 | unsupported payment-route 正例、提现证据反例与普通退款时效相邻正例 |

这些修改只能证明合同和确定性机制已对齐，不能把历史输出重写成当前 Runtime 的在线通过结果。三个 Agent Case 与三个 Grounding Case 的真实模型改善仍必须由一次固定范围、不可重试到通过的最小在线复测确认。

## 当前权威快照｜最终公开收口

当前运行时代码 `9c7c29045c28446b16a609768cd4b4c1202f8a51` 的最新真实结果：DeepSeek main 72/72、supplemental 36/36（开发期回归、非独立盲测）、FastAPI 365、Grounding 15/15、deterministic 478/478、现场 122/122。补充集合的历史文件名可含 `holdout`，公开口径已统一降级为 supplemental evaluation set；历史失败仍保留，不能与当前结果合并。

## 历史审计记录（以下内容不代表当前 Commit）

本文件保留历史评测中的失败发现，避免把旧数字误读为当前提交的质量结论。每次报告都必须绑定 Runtime Commit、suite/fixture SHA-256、模型与 Prompt 版本、命令和退出码；提交号不一致的报告标记为 stale，不与当前结果合并。

## 历史发现

- 早期 `live_model_synthetic` 报告曾暴露必要 Skill/事实缺失、Proposal/恢复缺失、重复调用和结构化输出失败。
- 早期 RAG2 Grounding 报告曾出现 `UNAPPROVED_EVIDENCE_SOURCE`。这类失败推动了最小来源集合约束和当前 15 条 `rag_grounding_cases.json` 的人工复核。
- 旧字段验收和 deterministic manifest 只证明合同或代表性路径，不等价于真实模型自然语言泛化、生产 SLA 或真实外部履约。

## 本轮修复方向

- Executor Prompt 增加任务事实、引用槽位、动作 Proposal、重复发现和失败停止的通用规则；Prompt 版本由 `agent_runtime_v3_0` 升为 `agent_runtime_v3_1`。
- Runtime 只接受服务端/当前 Artifact 的 opaque reference；同一回合重复只读调用不会继续消耗预算；失败或不可用 Skill 会留下限制码，不能被模型 `finish` 覆盖。
- Skill Catalog 为交易动作声明只读前置能力；评测网关只暴露自身拥有 fixture 的只读 Skill，避免把不存在的适配器误报为模型失败。
- Action Schema 明确 `create_after_sales_draft` 的安全引用字段；幂等键仍由 Runtime 生成，Java 仍是最终写入权威。

## 当前结论

真实模型结果必须按当前提交的最新报告读取。即使某轮通过率提升，也不能删除失败 Case、把合成网关结果写成真实业务成功，或由 LLM-as-a-Judge 覆盖硬失败。新失败先进入本文件和失败矩阵；只有抽象为通用缺口并补回归测试后，才可调整 Prompt、Schema 或 Skill 元数据。

## 2026-09-12｜当前代码闭环

当前运行时代码 `52d5482455e2389cfd6c2ef15d233712607ffa9f` 的通用修复已形成可回归证据：

- Prompt 版本升至 `agent_runtime_v3_3`，对售后草案在订单事实已验证但类型未明时只形成未提交 draft，不猜四类业务类型；`task_runtime` 还会在申请摘要不能替代订单事实时强制只读补查 order fact。
- 已验证事实出现 resolution candidate 时，服务端拒绝无必要的重复 `spawn_subtask`；服务端 repair 会安全结束，不增加无关 Skill 调用。
- 受影响 Runtime 回归：`mall-ai-service/.venv/Scripts/python.exe -m pytest -q` 全量 **362 passed**；live main `72/72`、holdout `36/36`，两套均为 synthetic read-only gateway。
- 旧失败数字仍作为归因材料保留：70/72、71/72 等历史运行不是“被删除”，而是证明缺口已被通用合同/服务端修复覆盖；当前报告的失败数为 0，仍不等于自然语言泛化率。
