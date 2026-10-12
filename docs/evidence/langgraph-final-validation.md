# 统一图补充验收结果

日期：2026-10-12。用户明确要求补齐真实模型质量测试、远程 CI 与完整回退测试。本记录不覆盖前一轮离线/环境报告；它们仍保留原执行工作区身份。

执行 Runtime Commit：`c142fe107fc5a9704f1dca68505dab84e8a95314`。实际 image revision 同该提交。源码指纹仍为 `01ae7bcbe682ceac475844505761d26406818be5450c03f67533877d7b651f64`；业务、Prompt、模型及 RAG 参数没有为本次测试修改。

## 真实 DeepSeek

使用独立账本 `tmp/langgraph-live-ledger-20261012/ledger.jsonl`，共享硬上限 80 HTTP attempts / 200,000 Token；没有运行历史客户的模型后台队列。

- 统一对话回归 9/9：问候不创建任务、缺信息追问、政策插问保留任务、同任务继续形成提案、文字确认不写入、会话隔离、刷新恢复、账号隔离、显式卡片撤回。
- 主业务链 1/1：读取真实 Java 订单、检索政策、构建处理方案、修改 Proposal、旧卡 409、Java 资格重校验与确认写入、回查、重复确认写入 0、跨账号泄漏 0。4 张浏览器业务帧通过采集核验，存于 `tmp/langgraph-live-showcase/browser/`。
- 累计 27 logical requests、28 HTTP attempts、27 成功、0 逻辑请求失败；73,996 Token。底层出现 1 次有界网络重试，不能写成无网络波动。
- 28 reservations / 28 settlements，未结算 0，对账通过。没有另起付费批次反复采样。

首次入口演练沿用未提交源码标识，不满足 Provider 守卫的 40 位提交 SHA 合同，2 次在网络调用前被拒绝（账本 testFailures=2、provider requests=0）。源码提交后绑定真实 SHA 和镜像身份继续；未放宽守卫。原拒绝记录已单独归档，累计账本保留原事件。

这些是本次迁移的真实模型功能冒烟，**不是历史完整评测集的重新验收或泛化率**。主集、补充集、Grounding 历史报告不被改写，也不与本次结果拼接。人工摘要和运营组分析后台模型任务本次保持关闭；其脚本合同和上一轮真实 Java 路径证据另列。

## 实际回退与恢复

回退脚本执行真实镜像切换，不是仅验证配置解析：

1. 停止新 AI/Web，切换保留旧镜像 `sha256:54a4c5def5567e1a9f8976d26182571de5219475b785bb11f721f3f2c251352f`。
2. 旧 AI 无宿主端口；反向代理只允许只读请求，封闭任务/人工交接等执行接口及所有变更方法；模型 Key 置空，worker 关闭。
3. 验证旧镜像身份、健康、Java 身份/售后列表读取、变更 503、任务接口 503、直接 AI 不暴露。
4. 停止旧入口，切回新镜像和 deterministic 配置；验证新图 API、身份和数据。

11/11 断言通过。默认领域任务集合 1,900 条、检查点 307 条、pending writes 3,433 条，回退前后内容 SHA-256 均为 `93dedea39b7a72999056fdf5529e4fe123b165f24041412f2aaea6d279800007`。没有删卷、清库或让旧执行器接管新图在途确认。

这是本机安全只读回退完整路径；不宣称生产灾备或生产恢复时间 SLA。AI/Web 已恢复新版，8 服务 healthy，Provider deterministic、live auth=0、模型后台作业关闭。

## 候选 CI 与工件

候选分支：`codex/langgraph-unification-acceptance`。已核实 `3837d4d5c22a90733fc4fd081d4dfcd0a483e15a`：

- [mall-ci #146](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/38220963661)：success。
- [quality-evaluation #149](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/38220963600)：success。

汇总、账本、原入口拒绝、两份 live 报告和回退报告长期归档在 [langgraph-final-validation](langgraph-final-validation/summary.json)。脚本与工件各有哈希，公开校验器核验预算、对账及绑定。Windows 原环境工件指定 `-text`，保留原字节；本轮新增工件直接生成 LF UTF-8。未覆盖历史证据。

`main` 未合并。这一补充证据提交的远程 CI 须另行精确核实，不用上述旧候选 CI 冒充；最终对用户反馈应提供最新已核实 SHA 的链接。
