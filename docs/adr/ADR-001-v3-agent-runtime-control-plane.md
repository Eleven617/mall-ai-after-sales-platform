# ADR-001：Mall v3.0 Agent Runtime 控制面

- 状态：已接受
- 日期：2026-09-03
- 决策范围：商品、订单、物流、库存、政策、售后与人工协同任务的统一编排

## 背景

此前客户入口以受限 Intent 和固定售后分支为主。它能安全处理单一问题，但无法自然完成跨商品、订单、物流、库存、政策和售后行动的开放目标，也会把对话理解与业务流程耦合在一起。

## 决策

建立领域限定的 E-Commerce Task Runtime。它不是通用自治 Agent，也不替代 Java 领域服务。

1. `commerce_executor` 只能输出受限的计划/执行 JSON，发现并调用版本化 Skill，观察 Artifact 后继续、重规划、等待用户、生成 ActionProposal 或结束。
2. `context_curator` 只接收 Artifact 的允许投影，生成版本化 Context Pack、工作记忆与受 owner 隔离的情景记忆；它不调用业务写 Skill。
3. `resolution_critic` 仅在候选方案比较、事实冲突、超过调查预算或高影响提交前触发；它只能提出缺口和排序理由，不能改变结果或自动提交。
4. Skill Catalog 是唯一能力来源。Runtime 对 Skill ID、版本、输入 Schema、输出 Schema、角色、action mode、owner scope、超时和预算做确定性校验。模型无权自创工具或越过 Catalog。
5. 订单、物流、库存、资格、售后、人工案件和业务行动仍经 Java API。Java 继续是 JWT、归属、资格、领域状态机、幂等、MySQL 事务、审计、Outbox 和 RabbitMQ 的唯一权威。
6. 所有写入相关 Skill 都统一经 `ActionProposal -> 客户确认 -> Java commit -> 回查`。Runtime 保存 action reference 与安全摘要；浏览器不持有内部 task、plan、artifact、action 或 Java 业务标识。
7. 任务、计划、Artifact、ActionProposal 和审计索引使用独立可追溯存储；Redis 仅用于锁、短期事件和缓存。已完成的 Java action 不能因 Runtime 重启而重放。

## 安全不变量

- FastAPI 不直连商城业务数据库，模型不拥有数据库、队列或管理员接口权限。
- 公开 DTO、Trace、Eval、Context Pack 不记录 Token、完整订单号、地址、手机号、原始客户消息、RAG 原文、完整工具结果、Prompt 或思维链。
- 模型结构错误、未知 Skill、越界参数、事实冲突、依赖超时、预算耗尽或确认失效都必须安全停止并产生受控 failure code。
- 运营分析 Agent 和 AI 质量评测 Agent 维持现有数据隔离；v3 Runtime 不赋予它们客户任务或业务写能力。

## 迁移策略

现有统一售后 LangGraph、诊断 ReAct、RAG、Java client、人工协同、Trace 和 Eval 作为 Skill/兼容适配器复用。旧 `/customer-service` 入口在迁移期保留为兼容接口，但不成为 v3 Task Runtime 的新控制面；新的开放任务从 `/agent-tasks` 进入。

## 非目标

不接入真实支付、仓储、维修、快递、ERP 或生产用户数据；不引入 Swarm、任意代码执行、通用 Skill Loader、长期无限记忆或自动改代码能力。
