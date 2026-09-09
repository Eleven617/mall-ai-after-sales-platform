# 简历/面试事实证据矩阵

| 可核验主张 | 代码/证据 | 当前结果 | 可以怎么说 | 不能扩大为 |
| --- | --- | --- | --- | --- |
| 统一售后 Agent | `customer_service.py`、`unified_after_sales_graph.py`、现场 122 case | 八类动作合同与现场路径通过 | “实现受限统一售后 Agent” | 生产级通用客服 |
| 任务感知与暂停恢复 | `task_orchestration_service.py`、`task_runtime.py`、durable 32/32 | 合成任务切换/恢复通过 | “支持可恢复任务摘要和单暂停槽设计” | 无限长期记忆 |
| Java 权威写入 | Portal Controller/Service、Build14A、Java 14/14 | 资格、owner、幂等、Outbox 通过 | “模型不直接写库，Java 做最终校验/事务写入” | 模型自主交易 |
| RAG 证据层 | `policy_retrieval.py`、`rag_evidence_verifier.py`、52 集 | Dense 默认；grounding 11/15 | “实现版本化政策检索与证据校验” | 52 集等于真实用户准确率 |
| 受限 Tool/Skill | `skill_catalog.py`、`tool_registry.py`、MCP 合同 | allow-list/角色隔离通过 | “工具选择受 Schema、权限和预算约束” | 任意工具调用 |
| Outbox/异步恢复 | Java publisher/receiver、fault 36/36、recovery 32/32 | 本机隔离 Compose 通过 | “覆盖幂等事件和故障恢复合同” | 生产消息 SLA |
| 人工协同 | `service_operations.py` 与 Java case service | 入队/领取/补件/处理/结案现场通过 | “支持 AI→人工协同闭环” | 全自动无人处理 |
| 前端展示 | Vue 页面与真实截图 | build/页面现场通过 | “提供客户、运营、质量三类安全工作台” | 在线 SaaS |
| 质量工程 | quality contract、manifest、GitHub CI | 17/17、478/478、CI success | “有可审计的合同评测与 CI 门禁” | 自动证明模型泛化 |

## 贡献边界

仓库明确是 `macrozheng/mall` 二次开发。个人新增/修改范围以 Git diff、提交记录和本项目文件为准；不把上游商品、订单、后台基础能力说成原创。AI 辅助生成的代码也不单独包装为人工原创，面试时说明自己负责的设计、审查、修改、测试和验证。

