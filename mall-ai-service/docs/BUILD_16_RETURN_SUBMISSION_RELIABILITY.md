# Build 16: 售后提交幂等与结果恢复

## 状态

- 已构建：是。
- Python 定向与全量测试：通过。
- Java 定向测试：通过。
- Vue 生产构建：通过。
- Docker 网页真实验收：已于 2026-08-13 通过本机 Docker 环境完成；不能把该结果称为生产上线。

## 解决的问题

旧流程在用户回复“确认”后，FastAPI 会先清除 Redis 中的退货方案，再请求 Java 创建售后单。
如果 Java 已写入而 HTTP 响应丢失，或 HTTP 已成功但返回内容损坏，FastAPI 无法判断是否成功，用户只能手动查看售后记录。

Build 16 改为由 Java 保存一条会员范围内的提交记录：`member_id + idempotency_key` 唯一。
相同确认方案的重复请求返回第一次创建的售后单，FastAPI 在响应不确定时保留原方案并查询结果。

## 客户可见行为

```text
确认退货
-> 正常返回：显示“已提交”和售后状态卡
-> Java 已创建但响应中断或返回内容损坏：系统提示正在确认，并自动查询
-> 已查到：显示同一张售后状态卡，不会新增第二张单
-> 尚未查到：保留原方案，客户再次“确认”时使用同一提交键安全重试
```

客户网页不显示 `proposal_id`、幂等键、Java 查询状态、内部异常原因或调试 Trace。

## 请求链

```text
Vue 确认消息
-> FastAPI 从 Redis 读取服务端方案和 proposal_id
-> FastAPI 携带 Bearer Token + idempotencyKey 调 Java
-> Java 以 JWT 确认当前会员，并校验订单、订单项和售后状态
-> Java 以 member_id + idempotency_key 防重复写入
-> Java 返回首次创建的售后单，或 FastAPI 通过状态查询恢复结果
-> FastAPI 投影客户安全 DTO
-> Vue 显示结果卡
```

## 三个重点文件

1. `mall2/mall-portal/src/main/java/com/macro/mall/portal/service/impl/OmsPortalOrderReturnApplyServiceImpl.java`
   - 在已有 JWT、订单和商品校验之后，以事务处理幂等占位、售后写入和结果绑定。
2. `app/services/return_application_service.py`
   - 保留同一 Redis 方案，在写结果未知时调用 Java 查询接口；明确结果后才清除方案。
3. `mall2/document/sql/migrations/V20260812__ai_return_submission_idempotency.sql`
   - 独立幂等提交记录表与唯一索引，不污染遗留售后业务表的历史语义。

## 关键取舍

- 采用独立提交记录表，拒绝直接修改遗留售后表的业务语义。
- 幂等键由服务端已有的不可预测 `proposal_id` 提供，浏览器不传也不展示它。
- 幂等键不是权限：Java 仍必须依据 Bearer Token 校验当前会员、订单归属、订单项归属与订单状态。
- 不新增 LLM、RAG、RabbitMQ、退款、物流或客户审核后台，因此无新增模型成本；正常提交只多一次轻量提交记录写入，网络不确定时才增加一次状态查询。

## 已通过的验证

- FastAPI 定向测试：30 条（客户端与售后提交流程）。
- Python 全量：138 条。
- Java `OmsPortalOrderReturnApplyServiceImplTest`：7 条，覆盖首次创建、同键复放、内容不匹配拒绝、跨会员不可见等场景。
- Vue `vue-tsc --noEmit && vite build`：通过。
- Compose 与迁移静态契约：通过。
- Docker 基础就绪检查：Vue、FastAPI、Java、MySQL、Redis、RabbitMQ、Mongo 均健康。
- Docker 真实客户链：经 Vue `/api` 代理完成登录 -> 真实 RAG 退货方案 -> 明确确认 -> Java 写入 ->
  客户售后状态卡与售后记录；客户响应未暴露 RAG 来源、工具结果、内部订单 ID 或幂等键。
- Docker 双账号边界：账号 B 看不到账号 A 的提交状态和售后记录。
- Docker Java 幂等复验：同一会员、同一幂等键、相同内容重复提交只返回同一 `application_id`；
  同键篡改内容被拒绝；另一会员的该键查询返回 `not_found`。

## 本机 Docker 验收范围与边界

已在本机 Docker 环境完成以下客户链：

```text
登录客户账号
-> 创建退货方案并确认
-> 验证状态卡出现
-> 以相同方案模拟响应中断或成功响应内容损坏后再次确认
-> 验证只得到同一 application_id，售后列表没有重复记录
```

本次证据是本机 Docker 真实联调，不是远程部署、生产流量、通用模型准确率或完整故障注入证明。
HTTP 响应中断/损坏后的恢复分支由定向测试覆盖；其跨进程故障注入留待后续可靠性演练，不能据此夸大为生产可用性承诺。
