# 评测演进与失败归因记录

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
