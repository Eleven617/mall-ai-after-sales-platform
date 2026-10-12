# 功能保留与验收矩阵

当前源码的无外部模型合同和本机实际环境分开记录。环境报告见 [验收汇总](../evidence/langgraph-acceptance/environment.json)。所有模型边界为 scripted/deterministic，不是 DeepSeek 质量结果。

该表描述初轮环境合同。后续已增加真实 DeepSeek 统一会话 9 项及确认写入主链、实际旧镜像只读回退 11 项和候选 CI；详见 [补充验证](../evidence/langgraph-final-validation.md)。没有将脚本模型结果改写为 live。

| 功能 | 实现路径 | 当前合同依据 | 当前实际环境 |
|---|---|---|---|
| 政策咨询 | ConversationGraph → 政策检索/核验 → 回答子图 | test_rag_service、既有 RAG 合同 | policy_question：真实本地索引，脚本判定/回答 |
| 单项查询 | 回答能力 → UnifiedSkillGateway → Java 适配器 | customer_service / business_tools 原合同 | single_query：真实授权订单查询 |
| 长任务与子任务 | TaskGraph prepare/decide/validate/read/curate/critic | test_task_runtime 及迁移合同 | long_task：提案到 Java 确认回查；子任务保留合同测试 |
| 多任务选择 | 仅选择当前 owner/session 的 task_ref | test_ambiguous_task_selection_never_guesses | multiple_task_selection / unselected_task_unchanged |
| 任务中插问 | 会话派发与任务线程独立 | policy_interruption、long_task_does_not_hold_conversation_lock | task_interruption：政策回答不推进任务 |
| 暂停与继续 | await_input / Command(resume) | checkpoint_restart_uses_same_wait_node_and_monotonic_budget | mongo_process_restart_resume；浏览器暂停链实际重启 |
| 待确认、修改、暂不提交 | 图 domain_action → 既有 Proposal 领域验证 | test_task_runtime 原确认/修改/过期/撤回合同 | proposal_amend_cancel：修改旧卡 409，撤回无写入 |
| 已有售后申请修改/取消 | 售后能力子图 → Java 版本/事务 | test_unified_after_sales_graph、既有 application 合同 | 全量合同通过；本轮未另做已提交申请全生命周期现场测试 |
| 人工交接 | 领域提案工厂登记等待检查点 → 显式确认 | test_human_handoff_v2、handoff_summary、handoff_semantic | human_handoff：领取、审阅、结案、重启查回、重复确认 |
| 运营分析与人工问题组 | 运营能力子图；原语义分析/Java 工作流不改 | test_build19_operations_agent、handoff_semantic | 实际 Java 聚合 + 脚本草稿；运营/改进页面通过，模型后台作业关闭 |
| Java 超时对账 | 原请求 key → 只读 reconcile | test_java_timeout_reconciles_original_key_after_runtime_restart | 真实写入后注入丢响应，AI 重启只查原 key；申请数仍为 1 |
| 中断模型调用恢复 | 非等待节点中断不重放 | test_crash_during_model_call_does_not_replay_on_recovery | mongo_crash_no_model_replay：真实持久化与新进程恢复 |
| 单记忆、隔离与删除 | 安全记忆接口 / 墓碑 / 全历史清理 | memory_retention、late_turn、request_dedup_and_scope | Mongo 删除/不复活/TTL/凭证不落库，Redis 跨进程锁 |
| 旧任务与图版本 | 旧卡拒绝、显式继续转换、未知提交仅对账 | old_confirmation、incompatible_graph_version | 旧记录只读聚合；合成 legacy 记录拒绝确认，未改实际旧记录 |

迁移专项 caseId 使用 `tests/test_graph_migration.py` 的完整函数名，fixture hash 与真实 JUnit 计数保存在 `docs/evidence/langgraph-migration-facts.json`。全部原单测均运行，不删除、不 skip。矩阵明确哪些分支仍只有合同测试，不将代表路径冒充全部业务分支的现场覆盖；本轮未执行旧 122 条 Runner，不复用历史 122/122。
