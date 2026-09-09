# Mall v3.0 最终交付状态

## 当前结论

**NOT_CLOSED**

本地代码、Docker 现场和证据包已经完成；在本次交接文档提交推送后，必须再次确认该最终提交的 `mall-ci` 与 `quality-evaluation` 均为 success，确认后才改为 `CLOSED`。

这里的 CLOSED 只表示本次约定的本地合成数据发布门禁已完成；它不表示生产上线、真实用户泛化、真实外部支付/仓储/物流/维修接入或生产 SLA。

## Git 与证据绑定

| 项目 | 值 |
| --- | --- |
| 仓库 | `Eleven617/mall-ai-after-sales-platform` |
| 分支 | `main` |
| 运行时代码提交 | `84e111d17e4117287660421ea5772a9ddcf44382` |
| 证据同步基线 | `5ea119970a2a4a9a9194dc3e1e46eff412bd406e` |
| 说明 | `5ea1199` 及本交接提交只增加证据/交接文档，不改变被测业务代码 |
| 工作区（复核开始） | clean |
| 远程 | `https://github.com/Eleven617/mall-ai-after-sales-platform.git` |

## 核心交付门禁

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| Docker/Compose | passed | Engine `29.7.2`；主 Compose 8/8 healthy；readiness 3/3 |
| 四类现场 Runner | passed | `field-20260909T105750Z-12222b15`，122/122，0 failed，0 blocked |
| Build 14A | passed | 负资格拒绝 + 正资格通过 + 归属隔离 + 幂等 + Outbox，脚本 exit 0 |
| FastAPI 回归 | passed | 353 passed，7 个子断言，1 条第三方弃用警告 |
| Java 定向测试 | passed | portal 14/14，admin 6/6，均显式 `-DskipTests=false` |
| Vue 构建 | passed | `npm run build` exit 0 |
| v3 deterministic gate | passed | manifest 478/478，preflight 8/8 |
| 远程 CI | passed（以当前文档提交最终复核） | `mall-ci` 与 `quality-evaluation` 均需与最终提交 SHA 对齐 |

## 现场 Runner 分项

| 类别 | 执行 | 通过 | 失败 | environment_blocked | 模式 |
| --- | ---: | ---: | ---: | ---: | --- |
| browser_e2e | 24 | 24 | 0 | 0 | live_browser |
| java_mysql_integration | 30 | 30 | 0 | 0 | live_java_mysql |
| fault_injection | 36 | 36 | 0 | 0 | isolated_compose_fault / runtime contract |
| durable_async_recovery | 32 | 32 | 0 | 0 | live_build21_restart_recovery |
| 合计 | **122** | **122** | **0** | **0** | 本机 Docker 与合成 Fixture |

现场报告：`tmp/field-acceptance/field-20260909T105750Z-12222b15/field-acceptance.json`。

- 报告 SHA-256：`6a301cd28072ebbf01fa07e81d7aaf5c4b2de9741c14ceb351122cac18f21567`
- Fixture SHA-256：`7573e19271528e904d2eb40cef2765f05d4e5f489f2b35cc1b1359bcd5128759`
- `testedCodeCommit`：`84e111d17e4117287660421ea5772a9ddcf44382`
- 运行时长：211947 ms

旧 Fixture 造成的 122 条阻断报告和更早提交的现场结果全部保留为 superseded/stale，不与本次结果相加。

## 仍然不能宣称

- 不是生产 SaaS、生产 SLA、真实吞吐或真实用户准确率。
- 没有接入真实支付、仓储、物流、维修系统；履约未配置时保持人工/未开始状态。
- live-model synthetic 结果是小规模合成评测，不能等同于自然语言泛化能力。
- 个人贡献边界不能从提交历史自动推断；上游 `macrozheng/mall` 能力不归为个人原创。
