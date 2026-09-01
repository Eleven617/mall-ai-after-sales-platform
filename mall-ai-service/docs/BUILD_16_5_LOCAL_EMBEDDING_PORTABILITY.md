# Build 16.5: 本地 Embedding 演示可移植性

## 目标与边界

本批次只替换 RAG 的“文本到向量”底座，消除客户演示对 Gemini、VPN 和云端
Embedding API 的依赖。完成本地与历史 Gemini 基线对比后，Gemini 运行链路和旧索引
已移除，不作为备用方案。

- 客户仍只看最终回答、事实卡和售后状态，不看 chunk、距离、来源或内部模型信息。
- Java 认证、订单归属、Redis 会话、LangGraph、RAG 证据核验和售后确认/写入流程不改变。
- DeepSeek 仍负责意图、证据核验和回答生成，因此本批次不是“整套 AI 完全断网”。
- 不以本地模型名替代质量证据；换模型后必须重建索引并重新测量。

## 方案

默认 provider 是项目内的 `BAAI/bge-small-zh-v1.5` FastEmbed ONNX CPU 模型：

```text
客户问题
-> 本地 ONNX Embedding（无网络、无 VPN）
-> local BGE 专属 Chroma collection
-> 距离候选
-> DeepSeek 证据核验
-> DeepSeek 政策回答
-> 客户安全 DTO
```

正式 collection 为 `mall_knowledge_local_bge_small_zh_v1_5`，metadata 写入固定的
`local` provider、模型和 512 维度。不同向量模型的结果不能混查；更换本地模型时必须
重建索引并重新测量。模型文件、维度或索引 metadata 不匹配时服务 fail closed。

## 实际构建状态（2026-08-13）

- 已安装并固定 `fastembed==0.8.0`；本地模型完整文件约 95MB。
- 已在项目目录加载模型并生成 512 维向量，无 Gemini HTTP 调用。
- 已以本地模型重建 15 个政策 chunk 的独立 Chroma collection。
- 36 条检索评测：原始 Top-3 支持题 `28/28`，距离门 `0.48` 下支持题 `28/28`。
- 不能沿用 Gemini 的 no-evidence 距离结论：本地 `0.48` 下原始距离门只拒绝 `3/8` 个
  无依据题；这正是为什么保留第二阶段语义证据核验，而非仅按向量距离回答。
- 本地向量 + DeepSeek 语义核验：支持题 `28/28`，无证据题 `8/8`。
- 15 条 grounding 合约：硬检查 `15/15`；人工复核信号 `14/15`，其中 1 条是措辞
  变化，不影响硬安全结论。
- Python 全量测试：`143/143` 通过。
- Docker 镜像已构建；无网络临时容器仍能生成 512 维本地向量；运行中的 FastAPI
  使用固定本地模型，健康检查通过；真实容器政策问答成功返回 1 个服务端来源。
- 本地评测相对历史 Gemini 基线保持相同的完整链路结果：支持题 `28/28`、无证据题
  `8/8`、grounding 硬检查 `15/15`。这只说明这组已审核问题上的表现相当，不代表
  任意业务场景、任意语料或生产准确率。
- 2026-08-13 已删除 Gemini Embedding provider、环境配置、旧 collection 及其孤立向量
  文件；删除前的可恢复快照在
  `snapshots/build16_5_remove_gemini_prechange_20260813`。

## 仍需用户配合的展示确认

1. 已在关闭 VPN、Docker 网络改为系统模式后，通过网页 `/api` 代理运行通用政策问答；
   客户响应得到政策答案。
2. 已确认客户响应只包含回答与业务卡片，不包含 `rag_sources`、chunk、distance、
   `tool_result` 或 `intent`。
3. 该网页点击确认不需要重新构建模型；本地 Embedding 不会访问任何云端 Embedding 服务。

DeepSeek 语义核验已在受控网络权限下完成；之前的 `WinError 10013` 只是受限执行环境
阻断，不能记录为本地 Embedding 的质量失败。

## 配置

```env
EMBEDDING_PROVIDER=local
LOCAL_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
LOCAL_EMBEDDING_MODEL_PATH=models/embedding/bge-small-zh-v1.5
LOCAL_EMBEDDING_DIMENSION=512
LOCAL_EMBEDDING_THREADS=1
```

Docker 中模型路径固定为 `/app/models/embedding/bge-small-zh-v1.5`。模型不是运行时下载，
因此演示现场不需要让 FastEmbed 访问 Hugging Face 或 Google。

## 运行时边界

本地 BGE 只负责“把问题和政策块变成可比较的向量”，不负责意图判断、证据裁决或最终
自然语言回答。当前链路仍会调用 DeepSeek 完成：

1. 意图判断：区分政策咨询、订单查询和受控售后申请；
2. 二阶段证据核验：判断检索候选是否真正覆盖问题；
3. 基于已核验证据生成回答。

因此本地 Embedding 不需要 VPN，也没有云端向量调用成本；DeepSeek 仍需要正常网络。
若 DeepSeek 不可达，系统应明确提示“智能客服服务暂时不可用”，不得假装是客户问题
表达不清，也不得用 Gemini 作为隐式备用。
