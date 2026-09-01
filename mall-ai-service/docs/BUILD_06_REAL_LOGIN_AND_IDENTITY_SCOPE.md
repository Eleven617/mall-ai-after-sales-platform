# Build 06：真实登录与会话身份作用域

## 目标

把本地“手工粘贴 Token”的联调方式换成真实 Java 会员登录，并证明同一个
浏览器会话编号不能让两个会员共享客服状态或访问彼此订单。

## 请求链

```text
Vue 登录表单
  -> FastAPI POST /auth/login
  -> Java POST /sso/login（Java 校验密码并签发 JWT）
  -> FastAPI GET /sso/info（Java 校验 JWT，得到 member_id）
  -> Vue 保存短期登录态

Vue 客服请求
  -> FastAPI 接收 public session_id + Authorization
  -> Java /sso/info 验证身份
  -> FastAPI 使用 hash(member_id, session_id) 读取会话状态
  -> 工具调用时把原 Bearer Token 转给 Java 订单接口
  -> Vue 只收到公共响应 DTO
```

FastAPI 不签发 JWT、不把密码交给模型，也不根据用户输入的 `user_id` 判断
订单归属。Java 仍是身份和订单事实的唯一权威。

## 本批次代码

- `app/routers/authentication.py`：`/auth/login` 与 `/auth/me`；
- `app/services/mall_client.py`：Java 登录、身份回读和安全错误映射；
- `app/services/conversation_scope.py`：会员 + 公共会话编号的服务端状态键；
- `app/routers/customer_service.py`：先验证 Java 身份，再进入客服编排；
- `app/services/tool_context.py`：保存本次请求的可信 `member_id`；
- `app/services/return_application_*`：退货草稿/方案绑定稳定会员身份，
  同一会员刷新 Token 后可以继续；旧字段名仍可读取；
- `mall-ai-web/src/App.vue`、`src/api.ts`、`src/types.ts`：真实登录、退出、
  登录态恢复和会话重置；
- `scripts/verify_auth_flow.py`：不依赖大模型的现场验收脚本。

## 离线验收

- Python：62 个单元测试通过；
- Vue：`vue-tsc --noEmit` 与 Vite production build 通过；
- 覆盖：登录转发、无效 Token、身份回读、同一公共会话 ID 的会员隔离、
  Token 刷新、旧 Redis 状态字段兼容；Java 意外返回不合规会员资料时，
  FastAPI 返回受控的 502 错误，而不是内部 500。

## 真实验收

已于 2026-08-03 用两个可删除本地测试账号完成真实验证。MySQL 在 3306、Redis
在 6379、Java mall 在 8085、FastAPI 在 8000 均实际运行。验证过程不记录或输出
密码、Bearer Token、收货信息或真实用户数据。

- A、B 均可通过 `FastAPI /auth/login` 登录，并由 Java `/sso/info` 回读身份；
- A 可查询 A 的订单，B 可查询 B 的订单；A 查 B、B 查 A、无 Token、无效 Token
  均被 Java 拒绝；
- 相同浏览器 `session_id` 在两个会员下会散列为不同 Redis 状态键；实际请求后的
  Redis 状态存在且有 24 小时 TTL；
- 真实“查物流”请求通过 DeepSeek 路由、FastAPI 工具层和 Java 订单摘要接口返回
  经业务系统核验的物流事实。

具体环境、售后闭环和已知限制见
[`BUILD_07_LOCAL_LIVE_INTEGRATION.md`](BUILD_07_LOCAL_LIVE_INTEGRATION.md)。

## 验收矩阵

| 场景 | 预期 |
|---|---|
| A 登录并读取 A 订单 | 已通过 |
| B 登录并读取 B 订单 | 已通过 |
| A 读取 B 订单 | 已通过：Java 拒绝 |
| B 读取 A 订单 | 已通过：Java 拒绝 |
| 无 Token 读取订单 | 已通过：拒绝 |
| 无效 Token 读取订单 | 已通过：拒绝 |
| 同一 `session_id` 切换会员 | 已通过：状态键不同 |
| 同一会员刷新 Token | 单测已覆盖；浏览器现场回归待 Demo 批次 |
