# RAG Chunking 与 Metadata Filtering：证据核对与最小硬化

**状态（2026-08-28）：** 已完成只读追踪、最小实现、本地索引重建、全量 Python
回归，以及 Docker / 网页代理真实模型验收。
这是对 Build 20 Dense 默认链路的结构/版本安全硬化，不是新的检索架构，也不改变
Hybrid/Rerank 的实验性定位。

## 1. 修改前的真实链路与配置

```text
app/knowledge/after_sales_policy.md
  -> chunk_markdown_file()
  -> local BAAI/bge-small-zh-v1.5 embedding (512 dimensions)
  -> Chroma PersistentClient / cosine HNSW collection
  -> Top-3 dense candidates / distance gate 0.48
  -> semantic evidence verifier
  -> DeepSeek grounded answer or abstention
```

修改前的真实状态，不是设计建议：

| 项目 | 修改前事实 |
| --- | --- |
| 政策源 | 一个 Markdown：`app/knowledge/after_sales_policy.md`，15 个二级标题规则。 |
| 切分 | 以 Markdown 标题切分；每个二级标题形成一个 chunk。 |
| 长度/overlap | 没有 `chunk_size`、最小/最大长度或 overlap 配置；当前 15 个块约 81–148 个字符。 |
| 标题/条件 | 保留 `document_title > section title`；当前源文档没有表格或嵌套条件标题。 |
| Chunk metadata | 只有 `chunk_id`、`title`、`source`、`document_name`、`section_path`。 |
| Embedding/索引 | 项目打包本地 `BAAI/bge-small-zh-v1.5`、512 维；Chroma collection `mall_knowledge_local_bge_small_zh_v1_5`、`hnsw:space=cosine`。 |
| 在线过滤 | 没有 Chroma `where`；所有当前政策 chunk 都直接参加 Dense 检索。 |

原始 52 条 `rag2-golden.v1` 覆盖 39 条应答和 13 条拒答的合成问题，以及两个
untrusted retrieval-text 注入夹具。它已覆盖口语改写、精确术语、近似误导、无答案、旧/新
规则语义问法和 prompt injection；但**没有**真实多版本文档、商品类别过滤、嵌套规则/例外、
Markdown 表格或 metadata pre-filter 的直接合同覆盖。

历史 36 条 `rag_cases.json` 是另一套检索集（28 条有依据、8 条无依据），15 条
`rag_grounding_cases.json` 是 grounding 合同；不能把它们与 52 条混为同一个指标。

## 2. 最小硬化后的 Chunk 契约

`app/services/chunking_service.py` 定义 `chunk-v2`：

```text
chunk_id, text, document_id, heading_path, source_order,
policy_version, effective_from, category, language,
document_type, content_hash
```

- 当前政策头部显式声明 `V1.1`、`2026-08-04`、`after_sales`、`zh-CN`、`policy`。
  `document_id` 由稳定文件名派生，`source_order` 由文档内顺序派生，`content_hash` 是正文块
  的 SHA-256；它们不是模型生成值。
- 主规则边界是 Markdown 二级标题。其三级及以下“条件、例外、处理表”等内容保留在同一个
  规则块；仅当单条规则超过 `MAX_CHUNK_CHARS=1200` 时，才按空段/句末边界打包。
- 目标长度为 800 字符，最小目标为 40 字符；小尾块只在不越过最大长度时合并。需要拆分时保留
  最多 80 个字符的局部 overlap。表格或无法安全断开的段落宁可超出目标，也不从中间切断。
- 当前 15 条真实规则都低于最大长度，因此仍是一标题一块、无 overlap。它们的正文和 chunk ID
  保持稳定；本次没有用机械小块来人为改变 Dense 排序。

### 可读真实证据（本机重建后）

```text
源：after_sales_policy.md / “退货运费”
chunk_id：08cc96bdba4ea2d5811f
heading_path：退货运费
source_order：2
policy_version：V1.1
effective_from：2026-08-04
category：after_sales
language：zh-CN
document_type：policy

查询：“商品质量问题退货，运费由谁承担？”
Dense Top-1：退货运费，cosine distance 0.231560
```

该 chunk 同时包含质量问题、个人原因和“不承诺全免运费”的边界，不是只截取一句结论。

## 3. Metadata Pre-filter 边界

在线客户政策链路现在先由服务端构建并传入 Chroma `where`：

```text
trusted publication config
  -> policy_version=V1.1
  -> effective_from <= server current date
  -> language=zh-CN
  -> document_type=policy
  -> Dense retrieval
```

`RAG_ACTIVE_POLICY_VERSION` 是发布配置，更新政策时必须由人同步更新并重新入库；模型、用户
文本和 RAG 文本都不能自行选择版本。对调用方给出的可信 category，系统只会在上述默认范围上
继续收窄，不会因为漏传字段而移除版本/日期/语言/类型约束。

目前 Java 订单快照提供商品名、属性和数量，**没有权威商品类别字段**。因此当前售后订单路径
不会伪造 `electronics`、`apparel` 等类别过滤，而是检索已发布的通用 `after_sales` 政策。
未来若 Java 提供 canonical category，服务端可显式传入 `PolicyMetadataFilter(category=...)`；
类别未知时仍是通用政策检索或追问，而不是让 LLM 猜类别。

Metadata 不替代事实：RAG 仍只给政策证据；Java 继续负责订单归属、商品、资格、状态机和写入；
模型 JSON 失败时仍由 P0 安全停止，不能偷偷进入 RAG、工具或写操作。

## 4. 新增结构/过滤评测

`evals/rag_chunk_metadata_cases.v1.json` 是 8 条版本化合成案例，零真实客户/订单/生产政策。
`scripts/evaluate_chunk_metadata.py` 只运行本地结构、预过滤和 BM25 合同，不调用 embedding 或 LLM。

覆盖：

1. V1/V2 同主题政策冲突与显式历史版本；
2. 生效日前排除未来版本；
3. 电子/服饰同主题类别隔离；
4. 规则、条件、例外同块；
5. Markdown 表格不与规则断开；
6. 语言/文档类型硬过滤；
7. 口语化“耳机坏了想退，运费谁出”在已过滤候选中的稳定命中；
8. 未知类别的空预过滤结果。

这套评测验证结构和硬范围，不声称它单独证明语义 Dense 检索或最终生成正确率。

## 5. 前后对比与实际验证

同一台本机、同一 `rag2-golden.v1` 52 条、Dense Top-3：

| 指标 | 硬化前 | 硬化后 | 结论 |
| --- | ---: | ---: | --- |
| Recall@3 | 1.000000 | 1.000000 | 保持。 |
| MRR | 0.948718 | 0.948718 | 保持。 |
| nDCG@3 | 0.962147 | 0.962147 | 保持。 |
| 本机检索平均时延 | 21.29 ms | 26.03 ms | 单次本机测量波动，不宣称性能提升。 |
| 本机检索 p95 | 12.59 ms | 15.99 ms | 同上。 |

附加证据：

- 政策结构校验：15 个真实 chunk，`chunk-v2` 合同有效；36 条检索/15 条 grounding 引用仍有效。
- 新增 metadata 合成套件：8/8 passed，零外部模型调用。
- 显式重新入库后，Chroma 中为 15 个 `chunk-v2` chunks；客户查询发现旧索引契约时会
  fail closed 并要求开发/发布动作重新入库，不会在请求内删除或重建持久化索引。
- Python 全量回归：`234 passed, 20 subtests passed`（一条第三方 `TestClient` 弃用警告）。
- 改后受预算限制的真实模型合成 grounding：前 8 条 Dense `8/8` passed，
  `environment_blocked=0`；端到端 p95 `3072.95 ms`，16 次模型调用、9911 tokens。
  未配置价格，因此不虚构成本；该 8 条样本不代表完整 52 条或生产准确率。
- Docker 八个常驻服务均 healthy、迁移容器成功退出后，经
  `http://127.0.0.1:5173/api/customer-service` 发送
  “商品质量问题退货，运费由谁承担？”：真实模型链路 HTTP 200、约 4479 ms，回答正确；
  公开 JSON 未包含 `rag_sources`、`rag_context`、工具结果、intent、trace、chunk 或版本字段。
  容器内的同一检索确认默认 scope 为 `V1.1 + 当日生效 + zh-CN + policy`，Top-1 为
  “退货运费”（`V1.1`、`2026-08-04`、`after_sales`）。
- 这是一次本机单路径验收，不把本地索引、合成评测或单次模型回复表述为线上部署证据。

## 6. 非目标和未证明项

- Dense 仍是默认；Hybrid/RRF/Rerank 没有因 Metadata 增加而转为默认。
- 未接入历史对话 RAG、长期记忆、第四 Agent、泛化框架或外部履约系统。
- 未新增 Java 商品类别 API；不能声称已经实现“按实际商品类别”线上过滤。
- 未用真实客户政策/订单数据验证多版本冲突，合成夹具不能代替真实发布流程。
- 未运行完整 52 条真实模型 grounding，也未重新执行所有客户/售后业务路径；本次不宣称线上部署、
 生产 SLA 或通用 RAG 准确率。

## 7. 复现命令

```powershell
cd C:\Users\12969\Desktop\mall\mall-ai-service
.\.venv\Scripts\python.exe scripts\validate_policy_corpus.py
.\.venv\Scripts\python.exe scripts\ingest_knowledge.py
.\.venv\Scripts\python.exe scripts\evaluate_chunk_metadata.py --summary
.\.venv\Scripts\python.exe scripts\evaluate_rag2.py --modes dense --summary
```

真实模型 grounding 是显式、受预算限制的开发检查，不进入客户请求：

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_rag2_grounding.py --mode dense --max-cases 8 --timeout-seconds 20 --max-attempts 1
```
