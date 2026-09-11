# Final Agent Failure Matrix

本表保留失败发现及修复链路；失败不会被删除或通过放宽断言掩盖。报告与当前运行时代码提交不一致时标为 stale。

| 阶段/报告 | 现象 | 根因/边界 | 修复或处理 | 当前状态 |
| --- | --- | --- | --- | --- |
| `main-final2` | 70/72；`agent-open-021` Proposal/过期后检查失败 | 任务恢复/Proposal 后置校验不稳定 | 增加服务端 proposal/恢复合同与回归 | 历史失败，当前主集 72/72 |
| `main-final3` | 71/72；`agent-open-011` 出现无关 `spawn_subtask` | 已有事实下模型重复扩展任务 | Runtime 识别已存在 resolution candidate 并安全修复 | 历史失败，当前主集 72/72 |
| `main-final4` | 71/72；`agent-open-009` 缺少订单事实 | 售后申请摘要不能替代订单事实 | `after_sales_list_requires_order_fact` 服务端修复 | 历史失败，当前主集 72/72 |
| Grounding 旧报告 | 11/15，4 条 `UNAPPROVED_EVIDENCE_SOURCE` | 旧报告绑定旧 Runtime/比较规则 | 重新执行当前 grounding runner；硬检查 57/57 | 当前 15/15，旧结果保留为历史 |
| Build 14A 退货状态 | 旧合成订单被 Java `return_refund` 资格拒绝 | 真实资格边界，不是脚本应绕过的错误 | 保留退出码 1，改用当前统一售后资格正/负路径验证 | 负向边界通过，不能伪造正向 |
| 旧现场 Runner | 122 条 `environment_blocked` | Docker Desktop IPC/Fixture 环境故障 | Docker 恢复后绑定新合成 Fixture 重跑 | superseded；当前 122/122 |
| 未确认写入 | 所有 live/field 场景 | 交易动作必须 Proposal + 确认 + Java | 比较器检查 `forbiddenSideEffects=0`、重复写为 0 | 当前通过 |

## 当前硬结论

当前主集、holdout、Grounding 和 122 条现场 Runner 都是当前代码/报告绑定的合成验证；它们不能被扩大为真实用户语言泛化、生产 SLA、真实外部履约或成本结论。后续只在 Runtime、Prompt、Schema、Skill、RAG 或业务边界发生实质变化时重跑对应套件。
