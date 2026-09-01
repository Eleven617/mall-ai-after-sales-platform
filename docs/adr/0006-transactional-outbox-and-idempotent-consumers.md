# ADR-0006：事务 Outbox 与幂等消费者

**状态：接受。**

售后申请、人工案件状态与相应 Outbox 记录在同一 MySQL 事务内提交。发布者随后将只含 opaque reference 的事件投递到 RabbitMQ；发布失败保留可重试状态，重复投递由消费者 delivery 记录和唯一约束去重。

`PUBLISHED` 仅表示 Broker 已接收，不等于客户通知、退款、补发或维修已完成。外部适配器未配置时必须展示待履约/待人工，不能伪造成功。
