# 前端统一展示升级验收记录

## 当前代码

- 当前发布 Commit：`67f5c938a8fddbf2b5f86c5a9f849dfbb94479d8`（已推送到 `origin/main`）
- 变更范围：`mall-ai-web/src/` 的客户页、开放任务 Agent、运营台、人工协同台、质量评测台和公共样式。
- 未修改：FastAPI/Java API、权限、数据库、Outbox、评测契约和业务写入逻辑。

## 已验证

```powershell
Push-Location .\mall-ai-web
npm run build
Pop-Location
```

结果：`vue-tsc --noEmit` 通过，Vite production build 通过，退出码 `0`。

```powershell
git diff --check
```

结果：通过。

```powershell
docker compose config --quiet
```

结果：通过，退出码 `0`。

发布提交 `eb2bd11` 的 GitHub Actions：[`mall-ci` run 34114454156](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34114454156) 与 [`quality-evaluation` run 34114454153](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34114454153) 均为 `success`。

## 本次展示改动

- 客户页：产品说明带、历史会话/对话/开放任务三栏；移动端按“任务→对话→记录”堆叠。
- Agent 工作台：状态中文映射、计划垂直时间线、事实/推导/方案标签、处理摘要折叠、行动确认卡和限制说明。
- 运营台：统一品牌外壳、统计窗口摘要卡、最高频转接原因和事实驱动的空/错状态。
- 人工协同台：统一品牌外壳、队列/详情布局和 `待领取 → 已领取 → 核验中 → 已处理 → 已结案` 步骤条。
- 质量评测台：统一品牌外壳、套件/Case/通过/失败摘要卡、RunManifest 折叠和 Case 详情折叠。

## 尚未现场验证

本机 Docker Desktop 当前未运行，`docker compose ps` 无法连接 Docker API。因此本次没有重新生成截图，也没有把旧素材标记为新版本。待 Docker 可用后，执行：

```powershell
.\scripts\start-demo.ps1
```

使用合成账号打开客户页、`/operations`、`/service-operations`、`/quality`，重新截取真实页面素材，再提交一个只包含 `docs/assets/` 与 README 说明的截图更新 commit。不得使用假数据或 ImageGen。
