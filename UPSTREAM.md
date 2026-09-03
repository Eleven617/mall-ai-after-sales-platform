# 上游归属与发布边界

本仓库根目录以 [Apache License 2.0](LICENSE) 发布。`mall2/` 基于 [macrozheng/mall](https://github.com/macrozheng/mall) 的 Spring Boot 商城代码库演进，保留其原始 Apache License 2.0 文件：[`mall2/LICENSE`](mall2/LICENSE)。本项目新增的 FastAPI、Vue、Compose、迁移、AI 售后、人工协同、评测和文档与上游商城原始能力有明确边界。

## 集成发布方式

公开仓库使用“单一集成仓库 + Java 源码快照/补丁边界”方式发布：根仓库同时包含 `mall-ai-service/`、`mall-ai-web/`、Compose、文档、评测和 `mall2/` Java 源码，但**不提交 `mall2/.git`**，也不把源码推回 `macrozheng/mall`。`mall2/` 的上游基线和本地改动可由其目录中的 Git 提交记录、`docs/evidence/v3.0-baseline-manifest.json` 与公开提交差异复核；发布提交的父提交来自个人集成仓库 `Eleven617/mall-ai-after-sales-platform`。

这意味着克隆者只需克隆本仓库即可取得可回放的 Java 源码，不需要访问上游作者的写权限；同时仍应把 `mall2/LICENSE`、根目录 `LICENSE`、`NOTICE`、上游版权和二次开发边界一起保留。该集成策略不是把上游代码宣称为原创。

发布或推送到公开仓库前必须：

1. 保留根目录 `LICENSE`、`NOTICE`、上游版权和 `mall2/LICENSE`；不得将上游代码表述为全部原创。
2. 确认 `.env`、`*.log`、浏览器存储、Docker 命名卷、Chroma 索引、模型权重、测试数据库导出、Token 和真实客户数据未被提交。
3. 仅保留合成演示账号/数据；不公开密码、密钥、真实订单、地址、手机号、客服原话或内部调试产物。
4. 对 FastAPI、Vue、模型权重与第三方依赖分别确认许可证；本文件不替代法律审查。
5. 发布时以“本地演示、受控边界、已验证范围和已知限制”描述，不能承诺生产 SLA、真实退款或外部仓储/物流接入。
