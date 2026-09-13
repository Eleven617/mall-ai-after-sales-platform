# 最终公开展示素材证据

## 当前状态：NOT_COMPLETE

当前被测 Runtime：`1b89500eae4c8f1c6195f7fed064745b300a3fbb`。本轮真实浏览器录制在第一步模型决策处收到 DeepSeek Provider HTTP 402（余额不足），没有使用 contract_mock 或旧素材顶替，因此三条最终 GIF 均为 `environment_blocked`，不能称为完成。无密钥探测报告：`tmp/showcase-provider-probe-20260913.json`，SHA-256 `3ab0b9eee428c630e39036ae363433408e62177a3b1f6c163d10bb5585fdccd8`。

| scenarioId | 当前状态 | 真实模型/写入/回查 | 当前阻断 |
| --- | --- | --- | --- |
| `showcase-main-closed-loop` | `environment_blocked` | 未观察到模型决策、用户确认后的 Java 写入或状态回查 | DeepSeek HTTP 402 |
| `showcase-pause-resume` | `environment_blocked` | 未生成同一任务的完整等待→保留→恢复素材 | 依赖真实 Agent 决策 |
| `showcase-fact-change-replan` | `environment_blocked` | 未生成事实版本变化后的重新核验/人工交接素材 | 依赖真实 Agent 决策 |

捕获入口：`scripts/Capture-PublicShowcase.ps1`。它只接受本地进程环境中的 Key，不输出 Key/密码/Token；失败即非零退出，不会把失败帧复制到公开目录。

## 历史审计记录（以下内容不代表当前 Commit）

以下内容是旧 Runtime/旧素材的审计记录，保留用于追溯，不能作为当前提交的展示完成证明。

生成时间：2026-09-12 UTC；公开素材绑定运行时代码 `9c7c29045c28446b16a609768cd4b4c1202f8a51`。

本组素材来自真实本地 Docker Compose、Vue/FastAPI/Java 页面、真实 DeepSeek 合成演示和脱敏合成 Fixture。截图不是图片生成或手工绘制；页面中的账号、订单、政策和案件均为合成数据。素材只展示安全 DTO、Artifact 摘要和待确认方案，不包含 Token、Key、完整订单号、原始 Prompt、原始 Trace 或业务数据库载荷。

## 主链

主链使用真实 `DeepSeekRuntimeProvider/deepseek-chat` 与本地服务完成：用户目标 → 缺少标识时澄清 → 订单/物流/库存/政策事实 → 候选方案 → 待确认方案（ActionProposal）。截图时停在确认前，因此截图本身没有执行 Java 写入；同一现场批次的统一售后 API/Java 验收覆盖了明确确认、资格/归属/幂等校验和合成申请状态返回。外部支付、仓储、物流和维修履约未接入，不能把待处理状态说成退款或补发完成。

| 素材 | 真实页面/含义 | 尺寸 | 大小 | SHA-256 |
| --- | --- | ---: | ---: | --- |
| `docs/assets/showcase-final/main-open-task-closed-loop.gif` | 主链真实页面帧：开放目标、事实卡、政策证据、候选方案和待确认卡 | animated | 431,780 bytes | `7a66aa8ab6ad79ee5e1b70d4b1b9ae0f4b707da2635d0b8ffe727f8de9a0c48b` |
| `docs/assets/showcase-final/main-open-task-result.png` | 主链结果页；可见版本化政策证据摘要和待确认方案 | 1440×1000 | 91,353 bytes | `7993bcd62b517f2cd6917552fb3acb16c7204f6683ec29478cbd6b7f5d02cf30` |

## 次级演示

| 素材 | 真实页面/边界 | 尺寸 | 大小 | SHA-256 |
| --- | --- | ---: | ---: | --- |
| `docs/assets/showcase-final/clarify-pause-resume.png` | 客户页的澄清/等待任务状态；完整暂停、政策岔开、自然恢复由 field/Build 21 合同和现场报告证明，本图不单独宣称完成全部序列 | 1440×1000 | 134,693 bytes | `217d18f07851ccc8c840a465172b2d0b4e0ab30e0a26c4b1993b700044e5c318` |
| `docs/assets/showcase-final/fact-change-replan-handoff.png` | 运营页合成事实不完整→“需要人工核实”的结构化交接；不伪装成真实仓储库存变更 | 1440×1000 | 116,294 bytes | `e51234d270f73158c1d8bfa660d04641566e54ec2c9f1840598fdfec6347ee91` |
| `docs/assets/showcase-final/operations-analysis.png` | 真实运营分析工作台：Java 聚合统计、证据部分完整、人工核实提示和转交列表 | 1440×1000 | 126,414 bytes | `9a14cd20c2667aec41ebfb1b0730d6284f2ba4e9be7a8a0131521ecbb20e259e` |
| `docs/assets/showcase-final/quality-evaluation.png` | 真实质量评测工作台：contract/mock 结果和安全边界 | 1440×1000 | 116,158 bytes | `65d14f2314abd811d16e26a91ebb80b44e8e7238699e5cef5cdaaabfb7789395` |

## 运行与证据绑定

- 主模型评测报告：`mall-ai-service/tmp/final-agent-quality-main-final-9c7c290.json`，SHA-256 `40cb0e25d09c13171f581ddd69050a4d4a06fccc7427c3c205df65919f49f400`。
- 补充评测报告：`mall-ai-service/tmp/final-agent-quality-supplemental-final-9c7c290.json`，SHA-256 `dd155133a5273ac29175e44ed0d4fe2f42d92296a9856f3cd382b436ac471604`；历史文件名仍可能含 `holdout`，但不作为独立盲测集公开。
- 现场报告：`tmp/field-acceptance-final-9c7c290/field-20260912T190322Z-6095525f/field-acceptance.json`，SHA-256 `6fcae42f1befeadd439957fe2bbecb114a77f787f29a8ec97fc29fdc6b016ff8`；合成 Fixture SHA-256 `4dd3d407001aec74e4c9546639c78eb2544b34a0ac4f2b6698eba345c27e3fc3`。
- 现场结果：browser 24/24、Java/MySQL 30/30、fault 36/36、durable recovery 32/32；这是本地合成现场，不是生产 SLA。
- 所有原始报告和临时 Fixture 保留在本机忽略目录，不提交 Git；公开只提交脱敏摘要、hash 和可复核路径。
