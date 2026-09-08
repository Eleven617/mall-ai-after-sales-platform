# 前端统一展示升级验收记录

## 当前代码

- 前端代码发布 Commit：`ddb466489dffcb2bec0ec15151e8cb0121518691`（已推送到 `origin/main`）；后续提交仅补充发布证据文档。
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

发布提交 `ddb4664` 的 GitHub Actions：[`mall-ci` run 34114651785](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34114651785) 与 [`quality-evaluation` run 34114651788](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34114651788) 均为 `success`。

## 截图资产与现场哈希（2026-09-07）

截图生成时的代码基线为 `3700dde210e9b7737a2181980c50a7885059ead3`；本节截图和文档在该基线之后作为发布证据提交。四张 PNG 均来自本地 Compose、真实 Chrome headless/CDP 和合成数据页面，未使用 ImageGen；哈希由 PowerShell `Get-FileHash -Algorithm SHA256` 计算。

| 文件 | 尺寸 | SHA-256 |
| --- | --- | --- |
| `docs/assets/agent-task-workspace.png` | `1399×1641` | `1ff2b70d10bed017148e0c9f4a1fbecf91a9eeb523febf6d2a5be55096afd251` |
| `docs/assets/customer-policy-conversation.png` | `1384×1641` | `693786e407a3d2fe8536f0892df53438c0c0351ab93123d779532b1fd9f6ce29` |
| `docs/assets/operations-handoff-overview.png` | `1369×1214` | `c14ec987d0d9d0e87367866acfbf1cedc60788735dad00ee1ced38a2a7655ff2` |
| `docs/assets/quality-evaluation-dashboard.png` | `1354×2710` | `d5a5ce42901dcf649b81c3bbbd2489851635fc105d6b1ee2d974833aae000593` |

该表是 `4dae57f` 发布提交时的历史资产指纹；2026-09-08 现场重截后的当前工作区指纹见文末补充，不与本表合并。

截图/证据提交 `4dae57fc8d0876fb2b343f898489750f8b95c4ab` 已推送到 `origin/main`，其 GitHub Actions 已完成：[`mall-ci` run 34179749694](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34179749694) 与 [`quality-evaluation` run 34179749709](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34179749709) 均为 `success`。这两个运行只证明该提交的既有门禁通过，不代表生产部署或真实模型泛化。

## 本次展示改动

- 客户页：产品说明带、历史会话/对话/开放任务三栏；移动端按“任务→对话→记录”堆叠。
- Agent 工作台：状态中文映射、计划垂直时间线、事实/推导/方案标签、处理摘要折叠、行动确认卡和限制说明。
- 运营台：统一品牌外壳、统计窗口摘要卡、最高频转接原因和事实驱动的空/错状态。
- 人工协同台：统一品牌外壳、队列/详情布局和 `待领取 → 已领取 → 核验中 → 已处理 → 已结案` 步骤条。
- 质量评测台：统一品牌外壳、套件/Case/通过/失败摘要卡、RunManifest 折叠和 Case 详情折叠。

## Docker 与浏览器现场复验（2026-09-07）

Docker Desktop 4.89.0 在 Windows 26200 上先后出现 AF_UNIX 运行时 socket 和 WSL 迁移路径故障。处理过程仅隔离了 `%LOCALAPPDATA%\Docker\run`、`%LOCALAPPDATA%\docker-secrets-engine` 运行时目录，并让 Docker 重新创建 `wsl\main` 目录；`D:\DockerData\DockerDesktopWSL\disk\docker_data.vhdx`、镜像、容器和命名卷均未删除或重置。之后 `docker info` 返回 Engine `29.7.2`，Compose 8 个常驻服务均为 `healthy`。

实际现场命令：

```powershell
docker compose config --quiet
docker compose up -d --no-build
docker compose ps
docker compose build mall-ai-web
docker compose up -d --no-build mall-ai-web
```

结果：Compose 配置通过；MySQL、Redis、Mongo、RabbitMQ、mall-portal、mall-admin、mall-ai-service、mall-ai-web 均健康；Web 镜像构建内含 `vue-tsc --noEmit` 与 Vite production build，退出码 `0`。

使用本地合成账号、真实 Chrome headless/CDP 和当前 Compose 页面重新生成了四张公开截图：

- `docs/assets/customer-policy-conversation.png`
- `docs/assets/agent-task-workspace.png`
- `docs/assets/operations-handoff-overview.png`
- `docs/assets/quality-evaluation-dashboard.png`

截图脚本只创建一个无业务写入的合成开放任务；模型若要求订单标识，页面展示安全等待/限制状态，不在公开图片中显示完整业务标识、Token、RAG 原文或原始工具载荷。

## 仍未现场验证的边界

本次截图现场不是完整浏览器 E2E 清单，也不等价于 Java/MySQL 全量集成、真实支付/仓储/物流/维修或生产 SLA。真实模型开放任务评测仍以 `docs/evidence/v3.0-current-head-evidence.md` 的分层结果为准，不能由截图外推准确率。

此前的待启动说明保留如下，供下一次复验参考：

```powershell
.\scripts\start-demo.ps1
```

使用合成账号打开客户页、`/operations`、`/service-operations`、`/quality`，重新截取真实页面素材，再提交一个只包含 `docs/assets/` 与 README 说明的截图更新 commit。不得使用假数据或 ImageGen。

## 2026-09-08 现场重截补充

Docker 恢复后再次使用真实 Chrome headless/CDP 和合成账号访问四个页面，截图脚本退出码 `0`。当前工作区资产指纹：

| 文件 | SHA-256 |
| --- | --- |
| `docs/assets/agent-task-workspace.png` | `cfa3e7a502d58fd02400a71285209aeb79db7bdbdcd37b5647b2be902ec8ac` |
| `docs/assets/customer-policy-conversation.png` | `56d5b8a645c4dbcf36a8b20d70c152175a0194f3dfaaa8b393832c4ff61b9b45` |
| `docs/assets/operations-handoff-overview.png` | `3676b9903c003847ee42962d24ae9c1d74630233ce4dae2b5486cdf41fb92ba1` |
| `docs/assets/quality-evaluation-dashboard.png` | `3ec40b0daf8b56df31a1d26f2799c188998e1ff631826ecbdbbcec28b49adaae` |

该现场仍只证明本地合成展示页面和公开字段边界，不证明完整浏览器 E2E 清单、真实模型泛化或生产能力。
