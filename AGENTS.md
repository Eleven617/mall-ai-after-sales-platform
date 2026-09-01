# Mall 工程协作规则

## 系统边界

- `mall2/` 的 Java 服务是业务事实、JWT、归属、资格、状态机、幂等、MySQL 事务和最终写入的唯一权威。
- `mall-ai-service/` 只负责受控编排、Schema 校验、公共 DTO、Redis 会话/待确认状态、RAG 与离线评测；不得直连商城业务数据库。
- `mall-ai-web/` 只能展示服务端公开 DTO，不能保存或提交内部 ID、角色权限决定、Token、RAG 原文、Trace 或业务写权限。
- LLM 只能建议有限 Schema 内的意图、字段线索或只读下一步。模型输出必须经过服务端白名单、参数校验、身份范围与事实核验；模型不能直接写订单、售后、退款或队列。
- 政策 RAG 是证据层，订单/物流/资格/售后状态必须走 Java。无证据、依赖失败或模型结构错误时安全停止，不用关键词或模型猜测替代事实。

## 数据与安全

- 不读取、回显、提交或记录 `.env`、密码、API Key、Bearer Token、原始客户对话、地址、手机号、订单号、完整工具载荷和 RAG 原文。
- Trace、EvalCase、FeedbackCandidate、RunManifest 只能使用版本化、合成或脱敏投影；新增字段先审查 allow-list。
- 角色隔离是硬规则：客户、运营、质量开发者、人工售后处理人员不复用 Token、页面、工具范围或 DTO。
- 创建、取消、修改或人工案件状态变化必须经 Java 身份/版本/幂等/审计/Outbox 校验。浏览器不得绕过 pending proposal/action 直达 Java 写接口。

## 数据库、消息与迁移

- 迁移只能新增 `mall2/document/sql/migrations/VyyyyMMdd__description.sql`；必须可审计、可重复执行，不能擅自删除现有演示数据或表。
- 业务状态、审计动作与 Outbox 写入必须在同一 Java 事务内。消息体只可携带 opaque reference，消费者必须幂等。
- 不执行 `git reset --hard`、`git checkout --`、`docker compose down`、卷删除或数据库清空，除非用户明确给出目标和授权。

## 变更与质量门槛

1. 先阅读受影响的代码、测试、迁移和 Compose，保留无关脏改动。
2. 所有文件编辑使用 `apply_patch`；不以脚本、重定向或 Python 直接写源码。
3. 改动 FastAPI：至少运行受影响测试；交付前运行 `.\.venv\Scripts\python.exe -m pytest -q`。
4. 改动 Java：显式传入 `"-DskipTests=false"` 运行受影响的 Maven 单测；根 POM 默认跳过测试。
5. 改动 Vue：运行 `npm run build`。
6. 改动 Compose、迁移或跨服务边界：运行 `docker compose config --quiet`，并在用户授权的本地 Docker 环境做真实路径验证。保留命名卷，不把本机结果表述为生产上线。
7. 任何新模型调用、数据可见性变化、角色/写入权限变化，先记录：用户可见性、实际验收路径、非目标、成本/延迟、失败回退。

## 常用验证

```powershell
# 从仓库根目录执行
Push-Location .\mall-ai-service
.\.venv\Scripts\python.exe -m pytest -q
Pop-Location

Push-Location .\mall-ai-web
npm run build
Pop-Location

Push-Location .\mall2
mvn -pl mall-portal -am "-Dtest=AiCaseHandoffServiceImplTest,AiServiceCaseServiceImplTest,AiServiceCaseOutboxPublisherTest,AiServiceCaseEventReceiverTest" "-DskipTests=false" "-Dsurefire.failIfNoSpecifiedTests=false" test
mvn -pl mall-admin -am "-Dtest=AiServiceOperationsServiceImplTest,AiServiceOperationsControllerTest" "-DskipTests=false" "-Dsurefire.failIfNoSpecifiedTests=false" test
Pop-Location
```
