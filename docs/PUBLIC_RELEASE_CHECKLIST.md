# 公开前检查清单

在创建或推送任何公开仓库前，由人完成以下检查。每次发布都必须有仓库维护者的明确授权；本清单本身不替代该授权。

## 内容与密钥

- [ ] 使用 `git status` 和受控的敏感扫描确认不存在 `.env`、Token、密码、API Key、服务间密钥、浏览器存储、日志、快照、数据库导出。
- [ ] 排除 `.venv`、`node_modules`、`target`、`dist`、Chroma 索引、模型/Reranker 权重、Redis/MySQL/Mongo/RabbitMQ 卷、临时目录和录屏缓存。
- [ ] Demo 账号、订单、政策、EvalCase、截图和录像均为可审计合成数据；没有地址、电话、真实聊天或真实订单号。

## 开源合规

- [ ] 保留根目录 `LICENSE`、`mall2/LICENSE`、`NOTICE`、`UPSTREAM.md`，并在 README 明确 macrozheng/mall 的 Apache-2.0 来源和二次开发范围。
- [ ] 人工审查 FastAPI、Vue、模型权重、数据集、Docker 镜像和其他第三方依赖许可证；本项目文档不替代法律意见。
- [ ] 不将上游商城、第三方模型或本地 Demo 表述为完全自主、生产部署或真实用户系统。

## 可复现性与证据

- [ ] 本地 Python、Java、Vue、Compose 合同与 Docker 演示均重新运行，结果记录在 `docs/TEST_AND_DEMO_EVIDENCE.md`。
- [ ] GitHub Actions 已在目标仓库实际运行；保留可公开的 Actions 链接/截图，未运行时不得显示“CI 已绿”。
- [ ] README 链接到架构、演示、评测、隐私边界、贡献矩阵、ADR 和已知限制。
- [ ] 录制两分钟演示前，按 `docs/demo-script.md` 逐步检查跨账号拒绝、无证据失败、只读 MCP 与人工案件边界。

## 发布描述

- [ ] 使用“本地合成 Demo”“已验证范围”“已知限制”描述。
- [ ] 不承诺生产 SLA、QPS、真实支付退款、真实第三方系统、在线多模型路由、模型训练或全输入准确率。
- [ ] 若任何检查未通过，保持私有 staging，不发布。
