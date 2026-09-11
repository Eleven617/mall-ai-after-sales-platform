# 评测演进与失败归因记录

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
