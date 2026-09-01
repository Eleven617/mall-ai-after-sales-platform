# AI 项目学习台账

> 目的：记录项目事实、学习进度和简历可用边界。它不是简历，也不把规划写成完成。
>
> 更新规则：只有“代码已实现 + 已有测试/联调证据 + 能用自己的话解释”才可以升级为“可作为核心项目能力”。

## 状态说明

- **已构建并讲过**：代码与至少一类验证证据存在，已完成第一轮结合代码的学习；面试前仍需用追问检验是否真正掌握。
- **已了解，待深化**：已接触概念或现有系统依赖，但还不能作为独立项目成果陈述。
- **待学习 / 待实现**：只在规划、技术选型或后续升级范围中，不能写成项目已完成能力。

## 一、已经构建并完成第一轮学习的项目能力

| 模块 | 已讲过的关键知识 | 已有项目证据 | 简历定位 |
| --- | --- | --- | --- |
| LLM 应用基础 | system/user/assistant/tool 消息、Prompt、结构化输出、Function Calling、Pydantic 校验 | FastAPI 的 Router / Service / Schema 分层与工具 Schema | 核心能力 |
| Agent 控制 | LangGraph StateGraph、自定义 ReAct、工具注册、最大步数、超时、重复调用、工具失败停止、结构化输出 | 客户诊断图、只读工具白名单、运营分析结构化草稿与隔离测试 | 核心能力；需能解释“图编排不等于持久化 Checkpointer” |
| RAG | Markdown 标题切分、Embedding、ChromaDB、向量候选、Top-K、距离阈值、证据验证、拒答 | 15 个演示政策章节、36 条检索评测、15 条 Grounding 合同 | 核心能力；必须说明是自建小规模评测 |
| 会话与售后流程 | session_id、会员身份 scope、Redis、事实/草稿/方案分开保存、确认与过期 | 退货草稿 - 核验 - 方案 - 一次确认 - 写入闭环 | 核心能力 |
| 权限边界 | Java 签发 Bearer Token、FastAPI 透传、Java 决定订单归属、双账号越权拒绝 | 本地 A/B 账号、订单读写边界验证 | 核心能力 |
| 评测与可靠性 | 单测、离线流程评测、Grounding 合同、Trace、失败分类、合成 EvalCase、确定性合同与可选模型归因 | Python 185 passed；质量专项 11 passed；离线质量脚本 9/9；Java 开发者角色 3/3 | 核心能力；不可表述为生产准确率或 GitHub Actions 已实际运行 |
| 受控 Multi-Agent | 客户诊断、运营分析、质量评测三种能力域；最小数据投影、角色隔离、确定性权限边界 | 客户/运营/开发者独立角色、CaseHandoff、401/403 拦截、无业务写入验收 | 核心能力；不是 Agent swarm，也不是三个模型自由协商 |
| 前端与交付 | Vue 状态、公共响应 DTO、Nginx、Docker Compose、健康检查、可删除演示数据 | 七服务本机运行和浏览器端到端演示 | 核心能力；仅限本地可复现交付 |

## 二、可写入“技能栏”，但需要按熟练度诚实表述的通用技术

### 可作为项目实战写法

- Python、FastAPI、Pydantic、httpx、REST API、JWT/Bearer Token 透传、Redis 会话状态、Vue 3、Docker Compose、Nginx、MySQL、pytest。
- DeepSeek Function Calling、LangGraph、受控 Multi-Agent、ChromaDB、Embedding、RAG 评测与证据验证、Synthetic Eval、结构化输出合同。

### 已了解或在现有 Java mall 环境中接触，后续需专题深化

- Spring Boot、MyBatis-Plus、Spring Security、RabbitMQ、MongoDB、Elasticsearch。
- 这些可以在技能栏按“了解/熟悉”出现；不能把 mall 原项目已有能力写成自己独立设计并上线的 AI 链路。

### 待学习或待实现，当前不能写成项目成果

- LangChain 迁移、Hybrid Retrieval、Rerank、Elasticsearch dense_vector、持久化 LangGraph Checkpointer、
  OpenTelemetry、MCP、A2A、Supervisor/Orchestrator-Workers、LLM-as-a-Judge、Long-term Memory、
  RabbitMQ 驱动 AI 异步消费、Kubernetes、云端生产部署。

## 三、简历事实库（后续只从这里取材）

1. 独立完成 FastAPI AI 服务、Vue 客服界面与 Java mall 真实业务集成。
2. 使用原生 Function Calling 和自定义 ReAct 处理受控只读工具调用；高风险售后写操作使用确定性校验和一次明确确认。
3. RAG 采用 ChromaDB 向量候选与 DeepSeek 语义证据验证；无证据或依赖故障时阻断售后方案/写入。
4. Java 签发身份凭证并完成订单归属校验；Redis 状态绑定已验证会员身份与会话标识；双账号证明越权拒绝。
5. Docker Compose 打包七服务本地环境，真实 Java API 创建可删除演示数据，并完成浏览器端到端演示。

## 四、后续学习顺序（Build 03-12 第一轮导读结束后）

1. **系统架构专题**：服务职责、数据所有权、同步/异步边界、故障隔离、为什么不是“技术堆砌”。
2. **Agent 专题**：ReAct、Function Calling、固定工作流、LangGraph 的适用条件和多 Agent 的边界。
3. **RAG 深化专题**：Chunk、Embedding、检索/重排、评测指标、Prompt/答案忠实性与成本延迟。
4. **通用工程专题**：HTTP、JWT、Redis、MySQL、MQ、Nginx、Docker、部署与可观测性；区分会用、能设计、能优化。
5. **项目面试专题**：从本项目代码和证据生成问题库，再进行模拟面试。

## 五、下一次简历更新时的规则

- 实习经历始终放在项目经历之前。
- 为互联网与制造业分别调整项目亮点、技能排序和自我介绍，不伪造两个不同项目。
- 每一条项目成果必须能回答：代码在哪里、如何验证、失败时怎么处理、它没有证明什么。

## 六、技术广度学习与主项目落地的双轨规则（2026-08-07）

### 原则

不把“学过概念”和“已在项目中实现”混为一谈。校招 AI 应用开发需要 T 型能力：一条
可以经受追问的深度主线，加上对主流框架、协议、检索、工程中间件的系统广度。

每个主题分为三层：

1. **能解释**：知道它解决什么问题、与相近方案如何取舍；
2. **能做最小实验**：可以在独立小实验中跑通最小案例并解释输入输出；
3. **能作为项目成果**：只有主项目真实需要、实现、测试并可演示后才写入项目经历。

### 必须学习的广度主题

| 主题 | 目标层级 | 是否立刻迁入主项目 | 进入主项目的条件 |
| --- | --- | --- | --- |
| LangChain | 能解释 + 最小实验 | 否 | 现有服务需要其抽象后能减少重复，而不是改名迁移。 |
| LangGraph | 能解释 + 最小状态图实验 | 暂不 | 已完成独立订单异常图实验：State / Node / 条件边 / interrupt / Command 恢复，以及“模型提议动作 + 图控制执行”的混合 Agent 图；8 个分支测试通过。诊断 Agent 出现复杂分支、暂停恢复、重试/人工接管后再评估迁入。 |
| MCP | 能解释协议、客户端/服务端与授权边界；后续最小本地实验 | 暂不 | 出现跨工具/跨系统标准化接入需求，且权限模型可控。 |
| Multi-Agent | 能解释 Router/Worker/Critic 的收益与状态同步成本 | 否 | 单 Agent 的工具、状态和评测已经不可维护，且有明确角色分工。 |
| Hybrid Retrieval / Rerank | 能解释并完成带评测的最小实验 | 暂不 | 现有评测显示候选召回或排序存在可量化缺口。 |
| Elasticsearch dense_vector | 能解释索引、过滤、召回和成本 | 暂不 | 商品检索规模或运营搜索需求真实出现。 |
| RabbitMQ / 异步 Worker | 能解释消息确认、幂等、死信、重试；后续最小实验 | 可作为 V3 候选 | 有真实订单事件到 AI 草稿/通知的异步场景。 |
| Docker / K8s / 可观测性 | Docker 深入；K8s 能解释核心对象；Trace/指标能实践 | Docker 已实践，K8s 暂不 | 需要多副本、滚动发布、资源编排或远端集群。 |

### 从外部 Agent 项目吸收的正确方式

- 学习 Tool Manager/能力白名单、离线评测沙箱、过程/结果指标、Trace、Skill 渐进披露、
  MCP 和多 Agent 的适用边界；不复制代码或为了关键词重写当前项目。
- 每学一个主题，先完成“概念 -> 最小实验 -> 是否值得迁入主项目”的闭环。
- 迁入主项目之前必须写清楚：当前痛点、替代方案、验收指标、增加的复杂度和回退方案。

### 大厂校招的能力证据标准

项目代码可以由 AI 辅助生成；候选人的核心竞争力是能够独立：

1. 将模糊业务问题转成验收案例和系统边界；
2. 判断模型、服务端、数据库和用户分别应该决定什么；
3. 通过日志、测试和真实联调发现问题，选择修复方案并验证没有引入回归；
4. 解释技术取舍、失败分支、指标含义和已知限制；
5. 在需求变化时安全地扩展功能，而不是只会让 AI 生成下一段代码。

## 七、V2 主项目学习与实施路线（Build 20—22，2026-08-20 规划）

> 这一节是后续主线提醒，不代表已经完成。顺序是：先做 RAG 的测量与升级，再做可恢复的
> Human-in-the-Loop 工作流，最后做 Agent 可靠性闭环；每个 Build 都必须有需求对齐、测试、
> 本机验收和可讲清的取舍。

| Build | 要学会的核心知识 | 项目中要完成的能力 | 不能误称的内容 |
| --- | --- | --- | --- |
| Build 20：RAG 2.0 | Dense Retrieval、BM25、Hybrid Retrieval、RRF、Cross-Encoder Reranker、Recall@K、MRR、nDCG、grounded answer、abstention、query rewrite、RAG prompt injection | 在同一黄金评测集上比较 dense 基线、Hybrid、Rerank；由证据、时延和成本决定默认链路 | 没有前后指标不能写“检索效果显著提升”；本地自建语料不能写“生产知识库准确率” |
| Build 21：Durable HITL | LangGraph Checkpointer、thread_id、Interrupt、Command Resume、persistent state、TTL、fault recovery、state sanitization、idempotent side effects | 一个可暂停、服务重启后可恢复、身份隔离的只读诊断路径；写操作仍在 Java 幂等边界内 | 不能把内存中的 graph state 叫 durable execution；不能把 Token/原话/原始工具结果放进 checkpoint |
| Build 22：Agent Reliability Closure | Agent Observability、Trajectory Evaluation、Agent Red Teaming、privacy-safe trace、evaluation flywheel、deterministic evaluator、Live Model Eval、LLM-as-a-Judge、OpenTelemetry 基础 | 安全 trace schema、轨迹断言、红队夹具；在合成数据上以真实模型回放 Prompt/Tool Schema/图；从人工确认失败到 EvalCase 和 CI 回归的闭环 | 不能把合成 live eval 叫线上监控或自动学习；硬安全规则不能交给 LLM Judge；不能声称模型会自动修复代码/Prompt/业务数据 |

### 每个 Build 的学习验收问题

在开始实现前、实现中和面试前，都要能自己回答：

1. 它解决的具体用户/工程问题是什么？不用它的替代方案是什么？
2. 模型、服务端确定性规则、Java 权限/数据库各自负责什么？
3. 输入数据来自哪里，哪些数据绝不能进入模型、日志、Trace 或持久化状态？
4. 用哪几个指标或失败案例证明它有效，而不是只证明“代码能跑”？
5. 新增复杂度、时延、成本、故障模式是什么；出现问题时如何降级或回退？

## 八、项目外的 Agent 技术 Lab（学习广度，不污染主项目）

> 每个 Lab 均按“能解释 → 最小实验 → 判断是否值得迁入主项目”推进。Lab 代码、Token、
> 数据和部署与 mall 主链隔离；完成 Lab 不等于可在简历中写成 mall 项目能力。

| 技术 | 先要学会什么 | 最小独立 Lab | 为什么暂不直接迁入售后主链 |
| --- | --- | --- | --- |
| MCP（Model Context Protocol） | Agent-to-Tool 标准、Client/Server、Tool Schema、Resource、授权与最小权限 | 用本地只读“政策检索”或“天气/待办”工具搭一个 MCP Server，再让独立 Agent Client 调用 | 当前商城工具均是内部受控 API；直接标准化暴露高权限订单/售后工具会扩大攻击面 |
| A2A（Agent2Agent Protocol） | Agent Card、Task、Agent Discovery、异步结果、跨系统身份与数据边界；理解它与 MCP 的区别 | 一个本地 Planner Agent 调用独立 Research Agent，交换脱敏任务与结果 | 当前三角色在同一项目、同一权限域中；没有跨团队/跨系统 Agent 互操作需求 |
| Supervisor / Orchestrator-Workers | Router、Manager-as-Tool、动态委派、并行 Worker、汇总、取消、预算、共享状态风险 | 用虚构的旅行规划或文档研究任务实现一个 Supervisor + 两个 read-only Worker，并记录成本/轨迹 | 固定角色售后流程需要可预测权限，当前不应让 LLM 自行分配业务角色或工具 |
| LLM-as-a-Judge | rubric 设计、位置偏差/自偏差、与人工标注一致性、pairwise judge、校准；与确定性规则的边界 | 用人工标注的小回答集比较“确定性合同”“LLM Judge”“人工标签”的一致性 | 业务安全、权限、敏感字段、写入禁止必须由确定性检查裁决，不能交给 Judge 投票 |
| Long-term Memory | short-term vs long-term memory、profile/fact/event memory、保留期、用户删除、遗忘、冲突解决、注入防护 | 用虚构用户偏好做带 TTL、查看、删除、跨账号隔离的 memory store | 售后聊天含订单与隐私；未先确定保留期、用户同意和删除语义前不能把它包装成“长期记忆” |
| OpenTelemetry | Trace/Span/Context、traceparent、attributes、sampling、metrics、logs、PII redaction | 用一个独立 FastAPI demo 串起 HTTP 请求、LLM 调用和工具调用 Span，并验证敏感字段不进 attributes | 主项目的安全 Trace schema 必须先定；不能先把原始聊天、Token、RAG 原文发送到可观测性后端 |

### 这六项技术的准确关系

```text
MCP：一个 Agent 如何标准化调用工具
A2A：不同系统的 Agent 如何标准化协作
Supervisor / Workers：一个系统内部如何动态分工
LLM-as-a-Judge：如何用模型辅助评测主观质量
Long-term Memory：如何跨会话保留经治理的信息
OpenTelemetry：如何以通用标准观察请求与执行链路
```

它们不是“用了 Agent 就必须全部接入”的套装。主项目负责深度和真实业务边界；独立 Lab
负责广度、对比和原理学习。只有出现真实痛点、完成需求对齐并有验收指标时，才把其中某项迁入
mall 项目，并同步更新 `AI_PROJECT_EVOLUTION_BACKLOG.md`。
