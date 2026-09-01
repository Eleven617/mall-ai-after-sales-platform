# 上游归属与发布边界

本仓库根目录以 [Apache License 2.0](LICENSE) 发布。`mall2/` 基于 [macrozheng/mall](https://github.com/macrozheng/mall) 的 Spring Boot 商城代码库演进，保留其原始 Apache License 2.0 文件：[`mall2/LICENSE`](mall2/LICENSE)。本项目新增的 FastAPI、Vue、Compose、迁移、AI 售后、人工协同、评测和文档与上游商城原始能力有明确边界。

发布或推送到公开仓库前必须：

1. 保留根目录 `LICENSE`、`NOTICE`、上游版权和 `mall2/LICENSE`；不得将上游代码表述为全部原创。
2. 确认 `.env`、`*.log`、浏览器存储、Docker 命名卷、Chroma 索引、模型权重、测试数据库导出、Token 和真实客户数据未被提交。
3. 仅保留合成演示账号/数据；不公开密码、密钥、真实订单、地址、手机号、客服原话或内部调试产物。
4. 对 FastAPI、Vue、模型权重与第三方依赖分别确认许可证；本文件不替代法律审查。
5. 发布时以“本地演示、受控边界、已验证范围和已知限制”描述，不能承诺生产 SLA、真实退款或外部仓储/物流接入。
