# 上游、二次开发与 AI 辅助贡献矩阵

| 范围 | 上游/既有基础 | 本项目二次开发与集成 | 人工决策与 AI 辅助边界 |
| --- | --- | --- | --- |
| 商城底座 | `mall2/` 源于 macrozheng/mall（Apache-2.0）；订单、会员、基础售后、Spring/MyBatis 结构 | 最小事实投影、统一售后适配、人工案件、幂等、Outbox/RabbitMQ 集成 | 不声称上游全部原创；人工确定 Java 为交易权威，AI 辅助实现/测试草案经审阅与验证后采用。 |
| AI 服务 | FastAPI/DeepSeek/Pydantic 等开源/服务依赖 | 受控 LangGraph、RAG、Schema 网关、Skill Catalog、Trace、质量评测、反馈治理、MCP | 人工决定权限/隐私/失败关闭；模型永不具有直接业务写入权限。 |
| 前端 | Vue 3/TypeScript 生态 | 消费者、运营、质量、人工处理页面与公开 DTO 投影 | 人工决定可见数据；页面不保存内部 ID 或权限事实。 |
| RAG/评测 | 本地 BGE、Chroma、BM25、Cross-Encoder 等第三方组件 | 审核政策、版本元数据、52 条黄金集、证据核验、合成 EvalCase/Profile | 只报告实际本机对比，不虚构生产准确率、成本或在线路由。 |
| 工程交付 | Docker、GitHub Actions、Maven/npm/pytest 工具链 | Compose 限制日志、启动脚本、ADR、测试与演示证据、发布检查 | 人工确认发布/密钥/许可证审查；AI 不自动上传 GitHub 或发布。 |

## 可如实说明的分工

AI 编程辅助参与了代码检索、实现草案、测试设计、文档与本地验证编排。人类负责并确认业务范围、数据最小化、角色隔离、Java 写入权威、确认/幂等、消息可靠性和验收口径。所有可对外声称的能力都应以当前代码、测试与演示证据为准。

上游归属、许可证和发布义务见 [UPSTREAM.md](../UPSTREAM.md) 与 [NOTICE](../NOTICE)。
