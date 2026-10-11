# 本机 DeepSeek 日常对话

日常入口 `scripts/start-demo.ps1` 默认启用真实 DeepSeek；`Prepare-PublicDemo.ps1 -SkipLiveModel` 或 `start-demo.ps1 -Offline` 保持离线。普通 `docker compose up -d` 会自动读取本机忽略的 `docker-compose.override.yml`。正式验收使用显式 base Compose，不自动加载此本机设置。

可见性：客户使用统一对话入口，系统决定直接回答或进入多步事项处理，两种路径均使用真实模型。Java 鉴权、用户确认和写入门禁不变。生成文本、耗时和实际费用取决于 Provider；超时/协议错误仍遵循现有失败处理。

调用产生真实费用，不做后台轮询模型。不修改或显示现有 Key。Web/API 仅绑定本机回环地址，避免将可计费聊天接口暴露给局域网。

用量隔离在被 Git 忽略的 `tmp/local-chat-usage/ledger.jsonl`，不复用历史在线评测账本、不创建正式 Release Lock。这是日常使用记录，不构成新的发布评测证据。沿用底层预算机制的字段名不代表正式批次。

累计保护为 600 次 HTTP attempts、1,600,000 Token，每次预留 12,000；重启不清零，达到门槛会停止请求。它不是货币费用保证，也不是无限调用授权。日后提高额度必须显式调整，不能删除账本绕过限制。

首次启用配置并启动：

```powershell
.\scripts\start-demo.ps1
```

暂时关闭真实调用：

```powershell
.\scripts\start-demo.ps1 -Offline -SkipBuild
```

验收：检查 Compose 配置、服务就绪、Key 仅做是否配置的布尔检查；用一条不含业务信息的问候验证真实响应与日常用量结算。不启动评测套件，不执行业务写入。
