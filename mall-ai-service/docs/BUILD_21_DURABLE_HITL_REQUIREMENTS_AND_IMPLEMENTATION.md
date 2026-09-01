# Build 21：可恢复 Human-in-the-Loop 订单诊断

> 状态（2026-08-25）：代码、Python 单元回归、Vue 生产构建、Docker 匿名恢复及登录双账号网站代理恢复/拒绝验收均已通过。本文不把该状态表述为生产上线、生产 SLA 或通用模型准确率证明。

## 1. 需求对齐

### 用户与数据可见性

- 客户只会看到“正在等待订单号 / SKU 编码”“补充后会继续只读诊断”“不会创建售后单、退款或修改订单”的安全说明。
- 浏览器不接收 checkpoint、`thread_id`、恢复句柄、Token、原始工具结果、RAG 原文或内部模型消息。
- `thread_id` 由 Java 已验证的 `member_id` 与服务器内部会话范围 HMAC 派生；浏览器不能指定。匿名会话与登录会员、不同会员之间生成不同线程。
- Redis checkpoint 只允许保存：`schema_version`、流程名、匿名化 owner fingerprint、等待字段类型、允许的只读工具名、状态、创建/过期时间、恢复次数和完成时间。
- Redis checkpoint 和 Trace 均禁止保存 Bearer Token、客户原话、完整订单号、运单号、RAG 原文、工具原始返回、模型 messages 或 Prompt。

### 一个真实验收路径

```text
登录客户询问“订单为什么未按预期完成、是否存在配送异常、我现在应如何处理”
-> 诊断 Agent 需要订单号，在 LangGraph interrupt() 暂停
-> Redis 保存脱敏等待状态，页面显示“等待订单号 / 仅只读”
-> 重启 mall-ai-service
-> 同一客户在同一会话提供订单号
-> 服务器以 owner-bound thread_id + Command(resume=opaque-ref) 恢复
-> 当前请求内调用原有 Java 只读物流/订单工具，展示事实卡
-> 不创建售后单、退款、订单变更或 Outbox 事件
```

### 非目标

- 不把含 Token、原话、订单/RAG/工具内容的完整 `DiagnosisState` 持久化；它仍是单请求内存状态。
- 不改变统一售后创建、取消、修改、Java JWT、状态机、幂等或 Build 18 Outbox。
- 不改 Build 20 的 Dense / Hybrid / Rerank 决策，不新增 Agent，不把客户请求送去质量评测。
- 不承诺在进程恰好于只读工具执行中崩溃时严格一次查询；该工具没有业务副作用，恢复时宁可要求客户重发标识，也不持久化原始恢复输入。

### 模型成本、延迟与回退

- 创建等待点只复用已有诊断模型决策，不为 checkpoint 额外调用 LLM。
- 恢复标识后直接继续已批准的只读工具调用；复杂订单异常会按事实门槛顺序核验订单再核验物流，不额外调用 LLM；因此不会增加 DeepSeek 成本。
- Redis 不可用、checkpoint 版本不兼容、已过期、并发恢复或恢复输入不明确时，系统停止或继续追问；不调用 Java 写接口。
- `Command(resume=...)` 只携带每个请求生成的随机 opaque reference。LangGraph 的 `__resume__` 写入在 saver 层被过滤；原始客户输入仅存在于本次请求内存。

## 2. 实际实现

### 核心链路

```text
ephemeral diagnosis graph 缺少 order_sn / sku_id
-> app/services/durable_diagnosis.py 构造 allow-listed StateGraph
-> interrupt(static safe payload)
-> RedisSanitizedCheckpointer（Redis，TTL 30 分钟）
-> 同一 owner/session 的下一条消息
-> 本地解析一个明确标识
-> Command(resume=opaque reference)
-> 当前内存中取原始输入、调用已批准的一项只读工具，或对复杂订单异常按顺序核验订单与物流
-> checkpoint 标记 completed；重复 resume 不重复查询
```

### 重点文件

| 文件 | 职责 |
| --- | --- |
| `app/services/durable_diagnosis.py` | 独立脱敏 State、HMAC owner-bound thread、Redis-backed LangGraph saver、`interrupt` / `Command(resume)`、TTL、版本、并发锁和敏感字段拒绝。 |
| `app/services/diagnosis_agent.py` | 保留原本富状态的单请求诊断图；只有缺标识时创建 Build 21 的最小 durable checkpoint。 |
| `app/services/customer_service.py` | 在新 LLM 路由前优先恢复已绑定的 checkpoint；成功后只展示原 Java 工具生成的事实卡。 |
| `app/schemas/customer_service.py`、`mall-ai-web/src/App.vue` | 公共卡片只增加安全布尔值 `resumable` 和说明文字，不泄露实现数据。 |
| `scripts/verify_build21_authenticated_live.py` | 使用临时本地 A/B 客户和订单，经 Vue 代理验证暂停、仅重启 AI 服务、owner-bound 恢复、重复恢复与跨账号拒绝；不打印或保存凭证、Token、订单号。 |

### 可靠性规则

1. `SanitizedMemorySaver.put_writes()` 丢弃 LangGraph 的特殊 `__resume__` 写入，防止原始订单号被存档。
2. 只有 `order_service`、`logistics_service`、`inventory_service` 可以成为可恢复等待工具；RAG 查询不能带着原始问题持久化。
3. 恢复前再次检验 owner fingerprint、TTL、schema version；完成 checkpoint 会保留短期 completed tombstone，重复恢复得到“未重复查询”。
4. Redis 锁让并发恢复返回可解释的“正在恢复”状态；业务写入不在该流程中。
5. 删除客户会话时先删除该 owner-bound checkpoint；无法确认删除时返回 503，不留下可恢复的已删除会话流程。

## 3. 验收与已知边界

已通过的自动化证据：

- `pytest -q`：`209 passed, 20 subtests passed`。
- 新增 durable 专项：Redis 持久化后的新 manager 恢复、敏感输入扫描、跨会员拒绝、过期、取消、输入歧义、重复恢复、版本不兼容、并发锁、Redis 不可用。
- 客服入口专项：首次 pause 不写旧 `pending_tool_call`，恢复不重新调用意图模型；复杂订单异常只按固定事实门槛读取订单和物流，不产生写入。
- `npm run build`：Vue 类型检查和生产构建通过。

已通过的本机 Docker 证据：

- 已通过 Docker 网站代理的匿名链路：真实 DeepSeek intent → `resumable=true` 等待卡 → 重启 `mall-ai-service` → 同会话 `Command(resume)` → Java 因未登录安全拒绝 → 重复 resume 不重复查询；Redis 记录只保留 `completed`，脱敏扫描未发现订单号、Bearer、原话、RAG、工具结果或 messages 明文。
- 2026-08-25 登录双账号网站代理链路：新建本地 A/B 账号及各自订单；A 在缺订单号时进入 `resumable=true` 等待卡，重启仅 `mall-ai-service` 后以同一会话补充标识并获得 Java 派生事实卡；重复恢复返回“未重复执行查询”；B 使用 A 会话在会话归属校验处被拒绝，未得到事实/诊断/RAG/工具载荷。A/B 前后的售后申请列表均未变化。

仍然存在的边界：

- 这不是支付/退款/售后写入的 durable workflow，也不证明多进程高并发下的生产 SLA。

## 4. 学习表达

Build 21 的重点不是“用了 Checkpointer 就更智能”，而是：

> LangGraph `interrupt` 解决可解释的人工输入暂停；Persistent Checkpointer 解决服务重启后仍知道在等什么；状态脱敏决定哪些数据根本不能进入持久化；Java 的身份、归属、状态机和幂等仍然控制任何写操作。
