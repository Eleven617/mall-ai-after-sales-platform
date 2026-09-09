# 本地运行手册与已知边界

## 启动与健康检查

在仓库根目录执行：

```powershell
docker compose config --quiet
docker compose up -d --no-build
Push-Location .\mall-ai-service
.\.venv\Scripts\python.exe scripts\verify_compose_stack.py
Pop-Location
```

预期是配置通过、8 个常驻服务 healthy、公开 readiness 3/3。不要执行 `docker compose down`、删卷、删 VHDX 或清空数据库来“修复”环境。

## 本地合成演示账号

使用 `scripts\Initialize-LocalDemoAccess.ps1 -DemoPassword (ConvertTo-SecureString ...) -PrepareCustomerFixtures` 初始化本机演示身份；密码只通过进程环境传递，不写 README、Git、报告或截图。演示页面只使用合成客户、订单和售后数据。

## 发布门禁

```powershell
Push-Location .\mall-ai-service
.\.venv\Scripts\python.exe scripts\validate_v3_release_manifest.py --json
.\.venv\Scripts\python.exe scripts\run_v3_release_preflight.py --json
.\.venv\Scripts\python.exe scripts\verify_field_acceptance.py --manifest ..\evals\v3\release-manifest.json --report-dir ..\tmp\field-acceptance --fixture ..\tmp\field-fixture-current.json
Pop-Location
```

Build 14A 使用 `tmp\run_build14.ps1`，它生成一次性 Fixture、运行正/负资格路径并清理临时 Fixture。不要把其中的账号、订单号或密码复制到公开材料。

## 常见失败处理

- Docker Engine 不可用：记录为 `environment_blocked`，先恢复 Docker，再重跑同一 Runner；不能把 manifest 注册数写成通过。
- Java 默认本地连接失败：检查临时 Compose 端口和 `allowPublicKeyRetrieval`，不要修改正式配置或跳过测试。
- 模型 Key/Provider 不可用：只运行 deterministic contract，真实模型结果写 `environment_blocked`，不退回关键词路由。
- Redis/RabbitMQ/Worker 重启：只在隔离 Compose 项目注入，等待 readiness 后重新执行幂等检查。
- 现场失败：保留失败 case、命令、退出码、Fixture hash 和报告；不得用 `skip`、`continue-on-error` 或放宽断言。

## 公开边界

禁止提交 `.env`、密钥、密码、Bearer Token、真实手机号/地址/订单号、原始客户原话、完整工具载荷、RAG 原文、Prompt 或思维链。截图和 JSON 只保留合成/脱敏投影。

未接入真实支付、仓储、物流、维修 Provider；履约默认 `NOT_STARTED`/`MANUAL_REQUIRED`。本仓库适合作品集和本地演示，不是生产 SaaS 部署。

