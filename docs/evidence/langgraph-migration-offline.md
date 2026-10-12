# 统一图迁移：本地离线验证

日期：2026-10-12。本文件记录零模型合同；授权后的真实本机验证另见 [环境记录](langgraph-migration-environment.md)。当前整体状态为 `LOCAL_MIGRATION_VALIDATED`。

后续真实 DeepSeek、候选 CI 和实际回退验证见 [补充验证](langgraph-final-validation.md)。以下未执行说明是该轮边界，不覆盖后续独立报告。

执行基线 HEAD：`60d53bd1fad3af444fd017f14035961427cca2c9`，执行时为未提交修改工作区，**不是冻结发布提交**。源码指纹：`01ae7bcbe682ceac475844505761d26406818be5450c03f67533877d7b651f64`。报告生成前后源码指纹一致。

| 检查 | 真实结果 |
|---|---|
| FastAPI 完整 pytest | 562 cases + 16 subtests，JUnit 578/578；0 failed、0 errors、0 skipped |
| 新迁移专项 | 18 条，全部通过，已包含在上述全量结果中 |
| 原 v3 manifest 合同 | 478/478 |
| 原 representative | 8/8 |
| Vue | vue-tsc / Vite build 成功 |
| Compose | `docker compose --env-file .env.example config --quiet`，exit 0；未启动服务 |
| 依赖一致性 | `pip check`：No broken requirements found |
| 公开证据校验 | 校验源码、JUnit、具名环境断言、原报告与验收脚本哈希 |
| Git 差异格式 | `git diff --check`，exit 0 |
| 外部 Provider | 本次没有调用外部模型 |

完整机器报告：`mall-ai-service/ci-evidence/langgraph-fastapi-report.json`，JUnit：`mall-ai-service/ci-evidence/langgraph-fastapi-junit.xml`。迁移 fixture SHA、caseId 和来源绑定见 `langgraph-migration-facts.json`。有一条现有 Starlette/httpx 弃用警告，不是断言失败。

新增测试覆盖：图等待节点恢复、模型调用中断不重放、凭证与业务标识不进入检查点、领域 CAS、可重建展示投影、旧确认失效、图版本不兼容、记忆全历史删除、删除墓碑、请求去重、插问隔离、长任务与会话锁分离、多任务选择、Java 原幂等请求查询、记忆 TTL、子图瞬态依赖、同任务并发、领域/检查点部分失败。

故障注入暴露并修复了一个实际迁移边界：检查点 `put` 失败不一定意味着 pending writes 中没有完整结果。新增持久化 invocation 收尾凭据，未正常结束的请求先恢复安全等待，不能以“下一节点已就绪”为由自动增加模型调用。

两条原测试曾断言保留原始历史，已按本次明确要求改成验证：不再持久化原文，业务事实仍在领域状态，安全片段只保存在唯一记忆仓。未 skip 或删除原用例。原 Prompt、意图合同、RAG 检索参数和 Java 业务规则没有调整。

## 与环境验证的关系

用户恢复授权后，真实 Mongo/Redis、Docker 重启、Java 原请求对账及浏览器现场已执行并独立归档。真实模型与远程 CI 尚未执行。已有历史 122/122、旧 live 评测和历史发布不作为此次迁移验收。

付费模型保持禁用。本机部署已切换，修改尚未提交或推送；原有未跟踪架构研究稿保留不动。
