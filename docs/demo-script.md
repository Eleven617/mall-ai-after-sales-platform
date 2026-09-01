# 本地最终演示脚本（13 步）

本脚本只适用于本地 Compose 与合成账号/数据。不要在录屏、终端输出或截图中展示 `.env`、密码、JWT、服务密钥、完整订单号、数据库内容或日志。

## 前置检查

```powershell
cd C:\Users\12969\Desktop\mall
docker compose ps
```

所有服务应为 `healthy`（`mysql-migrate` 为一次性成功退出）。若需更新镜像，使用 `docker compose up -d --build`；不得使用 `docker compose down` 或删除命名卷。

如果你没有已知的本地演示账号，先在自己的终端设置一次密码并准备合成客户夹具；脚本不打印或保存密码：

```powershell
cd C:\Users\12969\Desktop\mall
.\scripts\Initialize-LocalDemoAccess.ps1 -PrepareCustomerFixtures
```

## 演示步骤

| # | 操作 | 现场应看到的结果 | 安全断言 |
| ---: | --- | --- | --- |
| 1 | 准备两个合成消费者、运营、质量开发者、人工处理人员账号。 | 只在本机登录，不把凭据录入素材。 | 不公开密码/Token。 |
| 2 | 消费者 A 创建会话，询问有依据的售后政策。 | 回答与政策来源卡片出现。 | 不显示 chunk、距离、RAG 原文或内部 intent。 |
| 3 | A 查询自己的订单或物流。 | Java 事实卡与查询时间出现。 | 实时事实不由 RAG/LLM 编造。 |
| 4 | 用订单异常或售后诉求形成草案。 | 显示类型、商品、原因、说明与“待确认”状态。 | 确认前 Java 无新申请。 |
| 5 | A 明确确认草案。 | Java 返回申请公开状态；随后可查询进度。 | 不是“模型已办理”；状态由 Java 返回。 |
| 6 | 重复点击/安全重试同一确认。 | 返回同一幂等结果，不重复创建。 | 申请/Outbox 无重复有效写入。 |
| 7 | 消费者 B 尝试读取 A 的会话、草案、申请或案件。 | 被拒绝或只能看到 B 自己的数据。 | 不泄露资源是否存在或其内容。 |
| 8 | 演示过期草案或事实版本变化。 | 旧确认被拒绝，需要重新读取事实。 | 不用历史模型文本绕过资格。 |
| 9 | 询问无依据政策、模拟工具异常或索引失配。 | 安全失败/澄清/人工引导。 | 不自由编造，不继续写入。 |
| 10 | 将复杂问题转为最小 Handoff；运营选择 7/30 天窗口并生成草稿。 | 运营只看到摘要和可信聚合，草稿明确“需人工采用”。 | 无订单写入、无原始客户聊天。 |
| 11 | 质量开发者运行 `contract_mock`，查看结果并审核一个已脱敏候选。 | 仅合成 EvalCase、安全投影、Profile、RunManifest。 | 不读取生产会话/订单/Trace；不会自动修改代码或 Prompt。 |
| 12 | MCP 客户端执行 `initialize`、`tools/list` 和一个已授权只读查询。 | 返回只读工具清单和最小投影。 | 写工具不存在；跨账号、额外字段、角色/URL/写参数均被拒绝。可用 `verify_mcp_authenticated_live.py` 经网站代理自动复验。 |
| 13 | 人工处理人员领取案件、请求补件/处理/结案；客户查看公开进度。 | Java 状态机和 Outbox 推进公开状态。 | 运营不能领取；客户看不到内部备注。 |

## 结束质量门

```powershell
cd C:\Users\12969\Desktop\mall\mall-ai-service
.\.venv\Scripts\python.exe -m pytest -q

cd C:\Users\12969\Desktop\mall\mall2
mvn -pl mall-portal -am "-Dtest=AiCaseHandoffServiceImplTest,AiServiceCaseServiceImplTest,AiServiceCaseOutboxPublisherTest,AiServiceCaseEventReceiverTest,AiAfterSalesApplicationServiceImplTest,AiAfterSalesApplicationControllerTest" "-DskipTests=false" "-Dsurefire.failIfNoSpecifiedTests=false" test
mvn -pl mall-admin -am "-Dtest=AiServiceOperationsServiceImplTest,AiServiceOperationsControllerTest,AiDeveloperControllerTest,AiAfterSalesReviewServiceImplTest,AiAfterSalesReviewControllerTest" "-DskipTests=false" "-Dsurefire.failIfNoSpecifiedTests=false" test

cd C:\Users\12969\Desktop\mall\mall-ai-web
npm run build

cd C:\Users\12969\Desktop\mall
docker compose config --quiet
```

执行结果、环境阻塞和未验证项必须写入 [TEST_AND_DEMO_EVIDENCE.md](TEST_AND_DEMO_EVIDENCE.md)，不要把未运行步骤标成完成。

若本机没有已有的 A/B 合成客户夹具，维护者可显式运行一次安全自举的统一售后或 MCP 验证；临时密码只存在于当前 PowerShell 进程，脚本不会输出它、Token、订单号或 MCP session。它们只新增本地合成记录，不删除既有演示数据：

```powershell
cd C:\Users\12969\Desktop\mall\mall-ai-service
$env:MALL_UNIFIED_BOOTSTRAP_LOCAL_DEMO = "true"
$env:MALL_LIVE_DEMO_PASSWORD = [guid]::NewGuid().ToString("N")
.\.venv\Scripts\python.exe scripts\verify_unified_after_sales_live.py

$env:MALL_MCP_BOOTSTRAP_LOCAL_DEMO = "true"
$env:MALL_LIVE_DEMO_PASSWORD = [guid]::NewGuid().ToString("N")
.\.venv\Scripts\python.exe scripts\verify_mcp_authenticated_live.py
```
