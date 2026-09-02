# 评测、Profile 与可回放边界

## 两档评测

| 档位 | 输入与依赖 | 何时运行 | 结果含义 |
| --- | --- | --- | --- |
| `contract_mock` | 版本化合成 EvalCase、模拟工具/聚合结果 | 每次本地回归与 CI | 稳定的确定性合同门：角色隔离、轨迹、证据停止、敏感字段、越权和业务写入声明。 |
| `live_model_synthetic` | 合成输入 + 真正模型调用 + 模拟业务结果 | Prompt、模型、工具 Schema、RAG 或 LangGraph 改动后手动/夜间/发版前 | 检查真实编排在合成环境的行为；网络/模型不可用标为 `environment_blocked`，不伪造质量成功。 |

客户请求绝不会等待 52 条 RAG 黄金集或质量 Agent 的评测。质量运行由质量开发者独立身份显式发起。

## GitHub CI 中的确定性质量门

`quality-evaluation` 工作流只运行无需模型 Key、Chroma 索引、生产数据库或真实客户数据的确定性范围：`quality-agent.v2` 的 17 条 `contract_mock`、质量 Agent 20 条 pytest 合同、RAG 2.0 55 条 pytest 合同、以及 8 条 Chunk/Metadata 合同。它还构建开发者质量页面，但不执行 `live_model_synthetic`。

真实模型合成评测仍只可在本地、手动、夜间或发版前显式发起。网络或模型服务不可用应记作 `environment_blocked`，不能因 CI 通过或失败而被误写为模型质量结论。远程 CI 的具体运行链接与安全扫描范围见 [公开发布记录](PUBLIC_RELEASE_RECORD.md)。

## 固定 Profile

`mall-ai-service/app/services/evaluation_profile_service.py` 固化以下版本化 Profile：

- `contract_mock/v1`：无模型调用，固定工具预算与 60 秒评测预算。
- `live_model_synthetic/v1`：仅在显式选择时调用已配置 DeepSeek；固定温度、最大模型/工具调用次数、超时和重试预算。

RunManifest 只保存关联安全引用、Skill/Profile/Prompt/Tool Schema/RAG 版本、夹具哈希、耗时、可获得的 provider token 和错误类别；它不保存输入原文、订单号、Token、RAG passage、Prompt 或完整 Trace。

## RAG 2.0 评测

政策集使用版本化的 52 条人工复核黄金题，覆盖同义改写、精确术语、近似误导、无答案、旧新规则冲突、恶意/无关检索文本与 RAG prompt injection。对比 Dense、BM25 + Dense + RRF、以及 Cross-Encoder rerank 时记录检索命中、依据、端到端合同、延迟和可获得成本。

当前小型本地政策语料的已审结论是：Dense 保持默认；Hybrid/Rerank 作为可复现实验保留。这个结论不等于在任意生产语料、任意模型或任意负载下都更好。

## 回放和人工治理

1. `contract_mock` 运行将同一批合成夹具的哈希和安全副本保存在进程内 Run Store，质量开发者可检查 `replay-status` 并显式重放。
2. Profile 缺失、版本变化、夹具丢失/哈希失配或 live model 运行都会拒绝安全回放，而不是悄悄换模型或样本。
3. 消费者反馈只能是 allow-list `reasonCode`；人工将其脱敏、抽象为合成候选，审批后才会加入本地回归运行。
4. 确定性比较器首先裁决通过/失败；LLM 仅能在确定性失败后提供失败归因和候选回归题，不能改变硬失败，也不能自动修改 Prompt、代码、政策或业务数据。

## 复跑命令

```powershell
cd C:\Users\12969\Desktop\mall\mall-ai-service
.\.venv\Scripts\python.exe scripts\run_quality_agent_evaluation.py
.\.venv\Scripts\python.exe scripts\evaluate_rag2.py
.\.venv\Scripts\python.exe scripts\evaluate_chunk_metadata.py --summary
```

网络、模型或本地依赖失败应记录为环境阻塞；不要把它解释为模型质量失败，也不要将本地小样本结果宣传为生产准确率、成本或 SLA。
