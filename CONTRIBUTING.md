# 贡献与本地验证

本项目是基于 Apache-2.0 开源 `macrozheng/mall` 的本地合成 Demo。提交前先阅读 [AGENTS.md](AGENTS.md)、[UPSTREAM.md](UPSTREAM.md)、[SECURITY.md](SECURITY.md) 与 [公开前检查清单](docs/PUBLIC_RELEASE_CHECKLIST.md)。

## 变更原则

- Java 是身份、事实、资格、状态机、幂等、事务、Outbox 和最终写入权威；FastAPI 不直连商城业务数据库。
- 不提交 `.env`、Token、密码、日志、数据库/Redis/RabbitMQ/Mongo 卷、Chroma 索引、模型权重、真实订单或原始聊天。
- 客户、运营、质量开发者、人工处理人员的 Token、页面、DTO、工具和写权限必须保持隔离。
- 新模型调用、角色权限或可见数据变化前，先记录用户可见性、验收路径、非目标、成本/延迟和失败回退。
- 不通过删除测试、放宽权限、吞掉异常或伪造完成状态来通过验收。

## 本地质量门

```powershell
cd C:\Users\12969\Desktop\mall\mall-ai-service
.\.venv\Scripts\python.exe -m pytest -q

cd C:\Users\12969\Desktop\mall\mall-ai-web
npm run build

cd C:\Users\12969\Desktop\mall
docker compose config --quiet
```

若改动 Java 人工协同、售后或 Outbox，请依照 [demo-script.md](docs/demo-script.md) 中的 Maven 定向测试执行。若改动 RAG、Profile、质量 Agent、工具 Schema 或 LangGraph，请运行 `contract_mock` 评测；真实模型合成评测只能显式发起，失败需区分质量问题和环境阻塞。

## 提交与发布

先在私有 staging 完成人工许可证、密钥、合成数据、测试和 Docker 演示审查。不要自动发布、不要上传镜像或凭据。对外描述仅可使用已经运行并记录在 [测试与演示证据](docs/TEST_AND_DEMO_EVIDENCE.md) 中的能力。

每个重大 Build 完成后，必须创建一个清晰的 Git 提交，并追加 [重大升级变更记录](docs/UPGRADE_CHANGELOG.md)：目标、实际改动、验证、已知边界和回退依据缺一不可。提交不代表验收通过；未运行项必须如实记录。
