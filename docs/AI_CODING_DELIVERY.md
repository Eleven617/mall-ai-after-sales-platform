# AI Coding 交付说明

## 交付范围

本项目实现并验证的业务范围以 `C:\Users\12969\Desktop\hermes\output\Mall_可信AI售后与AgentOps平台_最终需求对接文档.md` 中 FR-01 至 FR-19 为基线：受控客户售后、政策 RAG、Java 最终写入、Outbox/RabbitMQ、三角色 AgentOps、只读 MCP、可靠性控制和人工协同案件闭环。

## AI 辅助与人工决定

AI 辅助用于代码检索、实现草案、测试设计、文档和本地验证编排。以下是人类必须并已明确决定的业务/安全边界，不能由模型自动改变：

- Java 是写入权威；模型不直接写交易数据。
- 客户写操作必须经待确认 proposal/action 与 Java 二次校验。
- RAG 只提供政策证据，实时事实只能来自 Java。
- 三个 AI 角色与人工处理人员的数据、工具、页面、身份严格分离。
- EvalCase 是合成/脱敏夹具；确定性合同优先于 LLM-as-a-Judge。
- Outbox、消费者幂等和失败队列是可靠性边界；未接外部系统不伪造成功。

## 交付纪律

- 变更通过审阅和自动化测试后才记录为已验证；没有运行的 Docker、模型或浏览器路径不得写成已完成。
- 未经人工批准，质量 Agent 不得自动修改 Prompt、代码、政策、权限、知识库或业务数据。
- 未来变更必须更新相关 ADR、测试与本文件的验证结论。

当前可复核命令与现场验收状态见 [TEST_AND_DEMO_EVIDENCE.md](TEST_AND_DEMO_EVIDENCE.md)。
