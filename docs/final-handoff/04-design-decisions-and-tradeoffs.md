# 设计决策与取舍

## Java 权威写入

LLM 不直连 mall2 数据库，也不能把自由文本当业务命令。AI 层只能提出结构化、带 TTL/owner/hash 的 Proposal；客户确认后，Java 再重读事实并执行 JWT、归属、资格、状态机、幂等和事务。代价是多一次确认和跨服务往返，收益是模型错误不会直接改变订单或售后状态。

## Agent 自由与 Workflow 确定性

任务感知 Agent 负责语义、任务切换、澄清和只读工具计划；Workflow 收缩到必须可审计的事实、资格、Proposal、确认和写入节点。这样不会把每轮对话硬编码成 pending 优先级，也不会把交易关口交给模型自由发挥。

## RAG 只做证据层

政策问题走 RAG；订单/物流/库存/资格状态走 Java。无证据或证据来源未批准时拒答/追问。Dense 在当前 52 条黄金集上更快且 Recall@1 更好，因此保持默认；Hybrid/Rerank 保留实验而不因“技术更全”强行上线。

## Redis、Checkpoint 与 Outbox

Redis 保存短期会话/任务摘要和锁，不是真实业务状态。Outbox 与业务写入在 Java 同一事务，RabbitMQ/消费者通过 opaque reference 和幂等处理。恢复时重新校验事实，不能把旧模型输出当作最新事实。

## MCP/Skill 白名单

Skill Catalog 和 Tool Registry 是能力边界；模型只能从注册版本中选择，只读调查工具有参数、身份范围、次数和超时预算。没有通用 Skill Loader、任意 MCP 或跨角色 Token 复用。

## 履约边界

支付、仓储、物流、维修外部系统尚未真实接入；默认状态保持 `NOT_STARTED`/`MANUAL_REQUIRED`，Demo adapter 明确标记为演示/测试，不伪造退款、补发或维修成功。

