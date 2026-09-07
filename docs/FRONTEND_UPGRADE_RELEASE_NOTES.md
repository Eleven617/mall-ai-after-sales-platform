# Mall AI 售后平台前端统一展示升级发布说明

## 范围

本次升级只调整 Vue 展示层，目标是让客户页、开放任务 Agent、运营工作台、人工协同处理台和质量评测台呈现为同一套可信电商 AI 产品体验。

## 已实现

- 客户页：产品说明带、历史会话/对话/开放任务三栏；移动端改为任务、对话、记录的纵向顺序。
- 开放任务 Agent：状态中文映射、计划垂直时间线、事实/推导/方案/不可用标签、处理摘要折叠、行动确认卡和限制说明。
- 运营台：统一品牌外壳、时间窗口摘要卡、转人工原因概览、事项与分析区域。
- 人工协同台：统一品牌外壳、案件队列/详情布局和 `待领取 → 已领取 → 核验中 → 已处理 → 已结案` 步骤条。
- 质量评测台：统一品牌外壳、套件/总数/通过/失败摘要卡、RunManifest 折叠和 Case 详情折叠。
- 公共样式：颜色、圆角、状态标签、时间线、摘要卡、空/错状态和 1440/1280/900/680/390px 响应式规则集中维护。

## 未改变的边界

- 未修改 FastAPI 或 Java API、权限、数据库、Agent 任务协议、Outbox、评测逻辑和最终写入链路。
- 前端不展示 Token、密码、内部任务 ID、原始 Prompt、原始工具参数、客户隐私或模型思维链。
- 没有新增假数据、假指标或重量级依赖。

## 当前证据

- 当前发布提交：`eb2bd11ff732709dded35ef5948957c5934b7619`，已推送到 `origin/main`。
- `mall-ai-web/npm run build`：通过，退出码 `0`。
- `git diff --check`：通过。
- `docker compose config --quiet`：通过。
- 当前提交对应的 [`mall-ci` run 34114454156](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34114454156) 与 [`quality-evaluation` run 34114454153](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34114454153) 均成功。
- 证据记录：[frontend-unified-upgrade.md](evidence/frontend-unified-upgrade.md)。

## 发布限制

- 当前工作站 Docker Linux 引擎未就绪，无法启动真实 Compose 演示并重新生成升级后的三张截图；`docs/assets/` 中现有素材仍是上一轮真实合成演示，不应标记为本次升级后的最终素材。
- 当前无法连接 GitHub `443`，因此本地提交尚未完成远程推送和当前 SHA 的 Actions 验证。
- 真实页面素材、远程 Actions、仓库 Description/Topics 需要在 Docker 与 GitHub 网络恢复后单独完成并记录。
