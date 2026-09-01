# 最终版统一售后：实施与收口计划

## 1. 批次目标与硬边界

本批次将现有客户入口中的售后能力收口为一个 **统一售后 LangGraph 子图**。它不是新建
一个独立客户 Agent：订单异常诊断图、政策 RAG 和统一售后图共同服务同一个客户客服入口。

LangGraph 只负责单次请求中的有界决策、查询、澄清和确认分支；Redis 继续保存跨消息的
草稿、待确认动作、候选目标及其会员/会话绑定。模型只能提出受限的结构化动作或线索，
不能获得内部 ID、JWT、写权限或绕过服务端校验。

### 用户与数据可见性

- 客户仅能看到自己的申请编号、申请状态、履约状态、真实处理说明、候选选择与确认卡。
- 客户响应不得包含 RAG 原文/chunk/分数、工具轨迹、Outbox、回调载荷、Token、内部 ID、
  管理员身份或运营数据。
- Java 继续作为 JWT、订单/申请归属、资格、状态机、幂等与业务写入的唯一事实边界。
- 管理员审核、受理、拒绝保留其既有真实角色边界；客户侧没有管理员写入口。

### 一条真实验收主线

登录客户提出“耳机坏了，想退货退款”
→ 统一售后图收集订单/商品/原因并核验资格和政策
→ FastAPI 持久化绑定用户与会话的 pending action
→ 客户明确确认
→ Java 事务内创建统一申请和履约命令 Outbox
→ 客户只看到“申请已受理 / 履约待处理”等真实状态
→ 无外部适配器配置时停在待履约或待人工，绝不伪造退款或发货成功。

### 明确非目标

- 不引入第四个 Agent、Agent swarm、MCP 迁移、Build 20 检索策略改造或自动 Prompt/政策修改。
- 不伪造支付、仓储、物流、维修外部系统成功；测试模拟适配器必须明确标识且默认关闭。
- 不将完整聊天、订单号、Token、RAG 文本、生产 trace 暴露给运营/质量页面。
- 不保留旧 `return_flow` 作为运行时回退；回滚依赖 Git tag 与数据库备份。

### 模型成本、延迟与失败回退

- 售后图优先复用现有受限 JSON 意图/字段提取；不让一个请求产生无界模型循环。
- 信息齐全时仅使用必要的受限模型决策和已有 RAG 证据核验；确认、读写、状态查询全由服务端
  和 Java 执行，不新增自由生成写操作。
- 模型、RAG 或只读工具失败时安全停止、澄清或建议人工，不创建/取消/修改申请。
- 写请求超时或响应损坏时按同一 pending action 的幂等键查询/重试，不重新生成动作。

## 2. 统一能力与状态模型

统一子图的受限意图为：`policy`、`eligibility`、`apply`、`list`、`status`、`cancel`、
`modify`、`follow_up`。四种申请类型为：`cancel_refund`、`return_refund`、`exchange`、
`repair`。

申请状态与履约状态独立：

| 维度 | 允许状态 |
| --- | --- |
| 申请 | `PENDING_REVIEW`、`ACCEPTED`、`REJECTED`、`CANCELLED`、`COMPLETED` |
| 履约 | `NOT_STARTED`、`PROCESSING`、`SUCCEEDED`、`FAILED`、`MANUAL_REQUIRED` |

对订单型申请，订单、商品和资格事实必须先完成；RAG 证据只裁决政策，不替代真实归属或资格。
多个订单、商品或申请候选一律向客户展示受控候选，不根据模型猜测目标。

## 3. 写操作协议

创建、取消和修改一律执行：

```text
受限动作 + 真实目标/资格 + 请求摘要
→ Redis 持久化 pending action（用户、会话、目标、内容哈希、TTL、幂等键）
→ 展示影响与确认卡
→ 客户明确确认
→ FastAPI 仅携带内部能力头调用 Java
→ Java 再校验 JWT、归属、合法状态、内容哈希与幂等
→ 业务数据与 Outbox 同一事务提交
```

浏览器不得直接构造可转发的 Java 写请求；过期、跨会话、跨账号、重复或篡改确认必须失败。

## 4. 履约与异步契约

| 申请类型 | 受理后的履约命令 | 未配置真实适配器时 |
| --- | --- | --- |
| 未支付取消 | 真实本地订单取消 | 可完成本地取消，仍记录状态 |
| 已支付取消退款 | 支付退款 | `NOT_STARTED` / `MANUAL_REQUIRED` |
| 退货退款 | 仓储收货后支付退款 | `NOT_STARTED` / `MANUAL_REQUIRED` |
| 换货 | 仓储收货后补发 | `NOT_STARTED` / `MANUAL_REQUIRED` |
| 维修 | 创建维修工单 | `NOT_STARTED` / `MANUAL_REQUIRED` |

Java 使用事务性 Outbox 发出命令；发布器与消费者有独立去重键，异步回调须经服务端鉴权、
申请归属/状态机校验和幂等审计。模拟适配器只用于测试/演示回执成功和失败，默认客户路径
不自动成功。

## 5. 实施顺序与变更清单

### A. 盘点与契约（本文件之后立即执行）

1. 列出现有 FastAPI `return_flow`、草稿、确认路由、公开 DTO、Vue 卡片及对应测试。
2. 列出现有 Java 旧退货单/Build 16 提交表/统一申请表、控制器、DAO、Mapper 与迁移。
3. 为统一申请、履约、pending action、回调事件建立显式 Schema/DTO 合同及不泄露字段测试。

### B. FastAPI 统一子图

计划修改/新增的核心区域：

- `app/services/after_sales_*`：统一 LangGraph 状态、受限决策、候选选择、follow-up 分支。
- `app/services/customer_service.py`、`intent_service.py`、`conversation_state.py`：自然语言入口
  只路由到统一子图，保留政策/RAG 和订单诊断子能力。
- `app/services/*pending*`、`mall_client.py`：服务器持久化 pending action 与 Java 内部调用。
- `app/schemas/*`、`app/routers/customer_service.py`：安全公共投影，不暴露内部字段。
- `mall-ai-web/src/*`：统一申请卡、候选选择、确认、列表/状态卡；删除旧退货专用 UI。

### C. Java 统一申请与履约

计划修改/新增的核心区域：

- `AiAfterSalesApplication*` 控制器、服务、DAO、Mapper、状态枚举：创建/list/status/cancel/modify，
  每次写入二次做 JWT、归属、资格、状态与幂等校验。
- 统一申请表补齐申请类型、履约状态、失败说明、动作指纹、审计时间；旧数据迁移脚本写入
  映射审计表。
- `AiAfterSalesOutbox*`：履约命令、发布、消费者去重、回调审计及明确测试模拟适配器。
- 管理员受理动作只改变允许的申请状态，并产生适当履约任务。

### D. 一次性迁移与旧路径清理

1. 创建只追加的迁移：备份/记录旧表总数，迁移至统一表，保存旧主键→新申请编号映射。
2. 对账旧/新总数、关键字段、会员归属、状态映射；失败即停止删除。
3. 对账通过后删除旧 `return_flow` 源码、旧公开接口、旧 Vue 卡片、旧测试及旧表/残留迁移。
4. 迁移报告记录版本、行数、空值/无法映射项；回滚使用迁移前数据库备份与 Git tag。

### 已确认的旧 AI 路径删除清单

以下项目是 Build 16 旧 AI 退货链路，不是商城原有的通用退货领域对象；统一链路验收及
迁移对账完成后必须删除：

- FastAPI：`schemas/return_application.py`、`services/return_application_service.py`、
  `services/return_application_state.py`，以及 `ConversationState` 中的
  `pending_return_*` 字段、`return_flow` 路由和 `/customer-service/return-applications`。
- Java：`AiReturn*` DTO/DAO/Mapper、`/returnApply/ai/*` 端点和
  `ai_return_submission` 表。保留商城原有 `/returnApply/create` 和
  `oms_order_return_apply`，因为它们不是 AI 链路，且迁移只归档 AI 提交所关联的历史记录。
- Vue：旧退货草稿/方案/记录卡及直连取消、修改接口；统一页面只能通过聊天确认卡发起写操作。
- 测试与文档：所有仅断言旧 `return_flow`、旧公开 API 或旧 `ai_return_submission` 的用例和
  说明必须替换为统一申请迁移、pending-action 和履约状态契约测试。

## 6. 验收矩阵

- 四种申请类型、政策/资格/list/status、cancel/modify 明确确认、follow-up 状态分支。
- 多订单/多商品/多申请歧义，跨账号、过期确认、重复确认、篡改动作、重复提交。
- 外部成功/失败/未配置、重复回调、Outbox 消息重复；任何情况下不虚构履约成功。
- Java/Python 定向与全量测试、Vue 构建、迁移对账、Docker 真实登录主线验收。
- 记录实际命令、结果和本机边界；不宣称生产上线、生产吞吐或通用模型准确率。

## 7. 2026-08-24 实施与本机验收记录（已完成）

### 实际收口结果

- 客服入口只使用统一售后 LangGraph 子图；旧 `return_flow`、旧 FastAPI 公开接口、旧 AI
  退货 Schema/服务/状态字段及 Java `AiReturn*` 已不在运行时源码中。
- 创建、取消、修改均通过 Redis 中会员+会话绑定的 pending proposal/action、内容哈希、TTL 和
  明确确认卡；浏览器没有可转发的 Java 写入口。多申请必须选择；最近已验证申请只可作为同一
  会员、同一会话的便利上下文，且每次均由 Java 当前会员列表重新确认。
- 申请状态与履约状态保持分离；默认适配器只停在待履约/待人工，不伪造退款、仓储、补发或维修
  成功。客户完成取消/修改后，公开卡显示“已取消”或“已更新”。
- 正常的新自然语言售后消息由一次受限结构化 Intent 模型按语义选择闭集 action，并统一进入
  `after_sales_flow`；已绑定 pending proposal/action 的“确认/取消”、标识符格式解析、权限、状态机与
  幂等仍由服务端处理。模型故障或非法结构化输出时安全停止，不用关键词猜测售后意图、RAG、工具或写操作。
- 为 MySQL 5.7 修正了迁移的 fail-closed 实现：该版本不能在 prepared statement 中执行
  `SIGNAL`，未通过对账时改为执行确定性 SQL 错误，仍阻止服务启动，不会假装迁移成功。

### 旧数据迁移与对账

- 执行前已生成可恢复的本机 MySQL 逻辑备份：
  `snapshots/unified-after-sales-db-backup-20260824-1629/mall.sql`。未执行 `docker compose down`，
  未删除命名卷或既有演示数据。
- 先从该备份恢复至隔离临时 MySQL，连续两次执行 `V20260824__unified_after_sales_finalization.sql`
  均通过，证明迁移可重复运行；临时容器随后已删除。
- 真实卷对账结果：历史 AI 提交为 0 行且迁移审计 `verified=1`；原活跃 Outbox 4 条、投递记录
  3 条均无可验证订单事实，因此没有伪造统一售后申请。它们以
  `LEGACY_RETURN_MISSING_ORDER` 原样归档并单独审计，活跃表中 `legacy_return=0`；旧
  `ai_return_submission` 仅保留归档表名，不存在旧运行时表名。商城原有
  `oms_order_return_apply` 未被修改。

### 实际验证证据

- Python 全量：`194 passed`；新增了明确售后状态/取消路由的合同测试。
- Java 售后定向：`mall-admin` 3/3、`mall-portal` 17/17。Outbox 测试日志中的 RabbitMQ 不可用
  是刻意注入的失败场景，测试本身通过。
- Vue：`npm run build`（`vue-tsc --noEmit` + Vite 生产构建）通过。
- Docker：MySQL、Redis、Mongo、RabbitMQ、mall-portal、mall-admin、FastAPI 与 Vue 网页共 8 个
  主服务 healthy；`mysql-migrate` 正常完成。
- 真实网页代理验收通过：以新建的本地演示客户登录并创建合规会话，完成 RAG 政策问答、统一
  申请方案与明确确认、售后状态查询、跨账号隔离、取消确认；公开响应递归检查未发现 RAG 文本、
  检索来源、工具结果、Token、Outbox、幂等键或内部 Trace 泄露。

### 已知边界与不作的宣称

- 以上只证明本机 Docker 与本地演示数据可用，不代表生产上线、生产吞吐、高可用或所有自然语言
  表达的准确率。
- 未接入真实支付、仓储、物流或维修外部系统；无配置时只能保持待履约/待人工，不能对客户声称
  已退款或已发货。
- 未完成跨进程崩溃注入、生产监控告警、外部回调大规模重放或取消后旧请求重试的完整状态机证明。
- 后续工作须按主线重新进行需求对齐；本批次没有启动 Build 20 的 Hybrid Retrieval / Rerank 或
  新增第四个 Agent。
