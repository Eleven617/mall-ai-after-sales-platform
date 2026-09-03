# 统一售后 Agent：任务感知对话与单暂停槽一次性升级方案

## 0. 决策摘要

本次不是在现有 `pending_*` 工作流外再叠加一层补丁，也不是逐步保留两套路由逻辑。应当进行一次性切换：

> 用“任务感知 Agent”接管每一轮消息的语义判断、任务切换与恢复；将 Workflow 收缩为事实查询、资格校验、Proposal、确认和 Java 最终写入等必须确定执行的边界。

升级完成后，系统的对话中枢不再是“哪个 pending 状态先命中”，而是模型依据当前消息、活动任务和唯一暂停任务判断：继续、临时岔开、恢复、放弃或开启新任务。

这不是取消 P0 Intent、Agent、LangGraph 或 Java 边界，而是重新分工：

```text
任务感知 P0 / Agent：理解用户当前在说什么，判断任务关系，决定追问与工具使用
任务运行时：保存、暂停、恢复最多一个未完成任务
Workflow：事实读取后的确定性编排、Proposal、确认、提交与恢复
Java mall2：权限、归属、资格、状态机、幂等、事务、最终写入
```

## 1. 背景与问题

当前实现中，存在待办售后、Durable 诊断或待执行工具时，入口会在模型理解新消息之前优先尝试恢复旧状态。结果是旧任务抢占新消息。

典型场景：

```text
用户：帮我查订单为什么还没发货
Agent：请提供订单号

用户：那我如果退款呢，邮费谁来出？
```

用户并不会刻意说“暂停刚才的订单诊断，我要问政策”。自然语言中的“那我如果退款呢”已经表达了临时切换到政策问题。理想行为是：

```text
模型识别：售后政策临时岔开，不是在补订单号
→ 保存订单诊断任务 A
→ RAG 回答退款运费政策
→ A 留为唯一可恢复任务

用户：订单号是……
→ 模型识别：这句话与暂停任务 A 匹配
→ 恢复订单诊断
```

当前问题不在于 Agent 不够聪明，而在于入口和多个 pending handler 在 Agent 之前抢走了消息解释权。

## 2. 升级目标

### 2.1 产品目标

1. 用户无需记忆“暂停”“继续”命令；模型应识别隐式切题、自然恢复和放弃意图。
2. 同一会话最多保留一个活动的未完成任务和一个暂停任务。
3. 单轮政策/聊天问题可临时打断任务，但不丢失原任务。
4. 用户再次提供原任务需要的资料、继续谈原话题或说“刚才那个”时，模型自动恢复正确任务。
5. Proposal、取消/修改确认等交易关口不能阻塞用户提出其他问题；它们应保留为可稍后确认或放弃的业务对象。
6. Agent 自主决定自然语言理解、任务关系、澄清顺序与只读工具计划；不把每个对话变化写成固定状态机分支。

### 2.2 非目标

1. 不支持无限数量的并行长期任务。
2. 不让模型自创工具、绕过 Java 或直接写商城业务数据。
3. 不把完整聊天记录、原始工具载荷或模型推理过程作为任务 checkpoint 保存。
4. 不把已提交业务动作伪装为可由 AI 层回滚；已提交后的取消、修改或补偿仍由 Java 状态机决定。

## 3. 核心产品模型

### 3.1 两个任务槽位与一个交易关口

```text
ConversationState
├─ active_task          当前未完成的多轮任务，至多一个
├─ paused_task          被临时搁置、可自然恢复的任务，至多一个
├─ transaction_gate     待确认 Proposal / cancel / modify，不抢占聊天
└─ facts / summary / recent_messages
```

这里必须区分“任务”和“交易关口”：

| 对象 | 例子 | 是否抢占下一条消息 |
| --- | --- | --- |
| active_task | 订单异常诊断，等待订单号 | 否，由模型先判断消息是否相关 |
| paused_task | 暂存的订单异常诊断 | 否，由模型判断是否应恢复 |
| transaction_gate | 已生成的退款 Proposal | 否，仅模型识别到确认/取消/修改时才处理 |

### 3.2 任务快照

新增服务端内部模型 `TaskSnapshot`。它保存恢复 Agent 所需的最小上下文，而不是保存整段 Prompt 或完整执行历史。

```python
TaskSnapshot:
    task_id: str                  # 服务端生成，浏览器不持有
    kind: TaskKind                # diagnosis / after_sales_draft / modification / ...
    status: TaskStatus            # active / paused / waiting_input
    goal_summary: str             # 面向模型的短目标摘要
    known_slots: dict[str, str]   # 已提取、已校验或待核验的任务字段
    pending_question: str | None  # 当前最适合补充的问题，不强制下一句回答
    completed_steps: list[str]    # 已完成的工具/调查步骤摘要或安全引用
    next_agent_hint: str | None   # 恢复时的简短运行提示
    created_at: float
    updated_at: float
    expires_at: float
```

建议 `TaskKind` 初始覆盖：

```text
order_diagnosis
after_sales_draft
after_sales_modification
```

`after_sales_policy` 和普通聊天通常是单轮任务，不必占用任务槽位；若后续确实需要多轮检索澄清，再成为 active task。

### 3.3 一回合的任务关系判断

P0 Intent 升级为“任务感知回合协调器”。每一轮模型同时输出业务意图与它和现有任务的关系。

```python
TaskRelation = Literal[
    "continue_active",        # 当前消息推进活动任务
    "temporary_detour",       # 临时回答一个新问题，暂停活动任务
    "resume_paused",          # 当前消息更适合恢复暂停任务
    "start_new_task",         # 开启新的多轮任务
    "standalone_answer",      # 单轮聊天/RAG，不创建长期任务
    "discard_active",         # 用户自然语言表达放弃当前任务
    "discard_paused",         # 用户自然语言表达放弃暂停任务
    "resolve_task_conflict",  # 两个未完成任务都不匹配，需自然澄清
]

TurnPlan:
    business_intent: IntentName
    task_relation: TaskRelation
    route: IntentRoute
    task_kind: TaskKind | None
    confirmation_intent: Literal["confirm", "cancel", "modify", "none"]
    rationale_code: str         # 仅用于 Trace/Eval 的有限枚举，不记录思维链
```

`TurnPlan` 是结构化的模型决策合同，不是固定工作流。模型可以识别各种自然表达，但服务端只接受有限字段和值。

## 4. 关键用户场景与期望行为

### 4.1 隐式切题：诊断 → 政策

```text
active_task：订单异常诊断，状态 waiting_input，缺订单号
paused_task：无

用户：那我如果退款呢，邮费谁来出？
```

期望模型输出：

```json
{
  "business_intent": "after_sales_policy",
  "task_relation": "temporary_detour",
  "route": "rag",
  "task_kind": null,
  "confirmation_intent": "none"
}
```

运行时：

```text
将 active_task 复制/转换为 paused_task
→ 清空 active_task
→ 执行 RAG
→ 返回带来源的政策回答
→ paused_task 仍为订单诊断
```

### 4.2 自然恢复：政策 → 诊断

```text
paused_task：订单异常诊断，等待订单号
用户：订单号是 123……
```

期望模型输出：

```json
{
  "business_intent": "query_order_status",
  "task_relation": "resume_paused",
  "route": "agent",
  "task_kind": "order_diagnosis",
  "confirmation_intent": "none"
}
```

运行时：

```text
paused_task → active_task
→ 恢复 Agent 上下文
→ Agent 选择 order_service、logistics_service、RAG 等必要工具
```

### 4.3 Proposal 不阻塞新问题

```text
transaction_gate：退款 Proposal，等待确认
用户：退货的邮费一般谁承担？
```

模型应输出 `after_sales_policy + standalone_answer`，RAG 正常回答，Proposal 保留。

```text
用户：那就按刚才的退款方案办
```

模型输出 `confirmation_intent=confirm`。服务端确认该意图只关联当前有效 Proposal，再交由 Java 最终校验与提交。

### 4.4 第三个未完成任务

```text
active_task：售后修改信息收集
paused_task：订单异常诊断
用户：我还要查另一笔订单的物流
```

模型先判断用户是在放弃其中一个、继续其中一个，还是确实要开启第三个任务：

- 语义明确放弃当前任务：丢弃 active_task，开启新任务；
- 语义明确恢复暂停任务：恢复 paused_task；
- 两者都不明确且新任务会成为长期任务：返回一条自然澄清，要求用户决定保留哪个任务；
- 不应静默覆盖任一任务，也不应积累第三个 paused task。

## 5. Agent、P0、Workflow 的最终职责

### 5.1 任务感知 P0

P0 保留，但从“当前句静态分类”升级为“当前回合协调”。它读取：

```text
当前用户消息
active_task 摘要
paused_task 摘要
transaction_gate 的公开摘要
必要的最近对话
```

它输出 `TurnPlan`，不再在 P0 阶段决定具体订单号、具体 Java 调用参数或业务结果。

### 5.2 统一售后 Agent

Agent 负责：

- 理解模糊表达、多意图表达与隐式切题；
- 判断是否要恢复/暂停/放弃任务；
- 决定当前最合适的澄清问题；
- 选择已注册的只读工具及调用顺序；
- 基于 Java 事实与 RAG 证据组织回答；
- 形成受限 Schema 内的售后草案字段。

### 5.3 Workflow 与 Java

Workflow 仅保留必须精确执行的节点：

```text
读取 Java 事实
→ Java 资格核验
→ 政策证据可用性核验
→ 创建 Proposal
→ 确认 / 撤回 / 修改
→ Java 最终写入及幂等恢复
```

Java mall2 始终是身份、归属、资格、状态机、幂等、事务和最终写入唯一权威。

## 6. 必须删除或替换的旧行为

本次必须一次性移除以下“旧 pending 优先”行为，不能与新任务协调器并存：

1. `customer_service.py` 中在 P0 之前无条件恢复 pending 售后、Durable 诊断或 pending tool call 的入口顺序。
2. `durable_diagnosis.py` 中将“缺订单号”作为默认 `interrupt()` 用例。
3. `conversation_state.py` 中把每条新消息直接解析为 pending tool 参数的默认行为。
4. `after_sales_application_service.py` 中 Proposal/Action 存在时，对所有非“确认/取消”消息直接返回固定拦截文案的行为。
5. `after_sales_application_service.py` 中用固定字段顺序主导对话的方式。字段完整性仍需校验，但 Agent 决定何时、以何种自然语言追问。
6. 前端将“暂停”仅表达为“补充字段或取消查询”的文案和交互。

## 7. 代码改造清单

### 7.1 Schema 与会话状态

涉及文件：

- `mall-ai-service/app/schemas/conversation.py`
- `mall-ai-service/app/schemas/intent.py`
- 新增 `mall-ai-service/app/schemas/task_orchestration.py`
- `mall-ai-service/app/services/conversation_state.py`

改造要求：

1. 新增 `TaskSnapshot`、`TaskKind`、`TaskStatus`、`TurnPlan`。
2. `ConversationState` 增加真正的 `active_task`、`paused_task` 和独立的 `transaction_gate` 引用；不再仅由 `pending_*` 字段临时推导 `active_task`。
3. 会话模型上下文向 LLM 提供 active/paused 的压缩摘要。
4. 浏览器不保存、提交或展示内部 task ID、checkpoint ID 或完整任务载荷。

### 7.2 P0 Intent 与任务关系识别

涉及文件：

- `mall-ai-service/app/services/intent_service.py`
- `mall-ai-service/app/schemas/intent.py`
- `mall-ai-service/app/services/structured_output_gateway.py`

改造要求：

1. `detect_intent()` 改为生成 `TurnPlan` 或以兼容方式返回包含 `TurnPlan` 的结构化结果。
2. Prompt 中删除“缺订单号后诊断 Agent 必须安全暂停”的规则。
3. Prompt 中增加 active/paused 任务关系判断规则与少量高质量示例。
4. P0 只输出业务意图、任务关系、路由和确认意图；不让它承担完整工具规划。
5. 对低置信度或两个任务都可能匹配的情况，返回自然澄清，而非关键词猜测。

### 7.3 统一入口重构

涉及文件：

- `mall-ai-service/app/services/customer_service.py`
- 新增 `mall-ai-service/app/services/task_orchestration_service.py`

目标入口：

```text
读取会话任务摘要
→ 调用任务感知 P0，得到 TurnPlan
→ TaskOrchestrationService 执行任务状态迁移
→ 路由到 Agent / RAG / 售后业务执行节点
→ 更新任务快照、交易关口和公开 DTO
```

具体要求：

1. 删除 P0 前的 pending 抢占分支。
2. `resume_paused` 时才恢复暂停任务。
3. `temporary_detour` 时保存 active_task，处理当前单轮请求。
4. `standalone_answer` 不改变暂停任务。
5. `discard_*` 时仅删除未提交任务状态；已提交业务对象不由该分支伪回滚。
6. 不再由入口按照多个 `pending_*` handler 的硬编码优先级决定消息归属。

### 7.4 诊断 Agent 与 Durable 状态

涉及文件：

- `mall-ai-service/app/services/diagnosis_agent.py`
- `mall-ai-service/app/services/durable_diagnosis.py`

改造要求：

1. 去掉 `require_order_identifier=True` 时“先固定解析订单号、再固定调用 `order_service`”的对话控制逻辑。
2. 缺订单号时，Agent 产生自然的 `waiting_input` 任务状态，不调用 `interrupt()`。
3. 保留 ReAct 的多工具能力：Agent 仍可在已注册工具范围内决定订单、物流、库存、政策的调用顺序。
4. `durable_diagnosis.py` 改为真正的任务暂存/恢复基础设施，或者在普通会话任务快照已足够时收缩为可选的 LangGraph checkpoint 实现。
5. 若保留 LangGraph `interrupt()`，它只能发生在 Agent 已判断需要暂存任务的安全节点；它是内部实现细节，前端不展示该术语。

### 7.5 统一售后与 Proposal

涉及文件：

- `mall-ai-service/app/services/unified_after_sales_graph.py`
- `mall-ai-service/app/services/after_sales_application_service.py`
- `mall-ai-service/app/services/after_sales_application_state.py`

改造要求：

1. 将统一售后图收缩为业务执行编排器，不再充当所有用户消息的第一解释者。
2. 售后草案字段可以无序收集；Agent 决定下一问，服务端在进入资格核验/Proposal 前检查字段完整性。
3. pending draft 遇到新话题时保存为 active/paused task，而不是吞掉消息。
4. pending Proposal、pending Action 迁移为 `transaction_gate`：保留、过期、确认、取消和 Java 恢复机制不变，但不得阻断政策/RAG/聊天/新任务。
5. “确认”不再仅依赖固定词面。模型可识别“那就按这个办”“可以，帮我提交”等自然表达，输出结构化确认意图；服务端只允许其作用于当前有效 transaction gate。
6. Java 写入前重读必要事实、执行 Java 资格/状态机/幂等校验的边界保留。

### 7.6 Skill Catalog 与工具

涉及文件：

- `mall-ai-service/app/services/skill_catalog.py`
- `mall-ai-service/app/services/tool_registry.py`

改造要求：

1. 保留固定 Skill Catalog 和工具 allow-list；这是 Agent 的能力边界，而不是对话 Workflow。
2. 替换 `select_customer_skill()` 对“旧 route → 固定 Skill”的过度决定逻辑，使其消费 `TurnPlan` 和 Agent 的任务类型。
3. Agent 在一个 Skill 的允许工具范围内自由规划下一步；服务端继续校验工具名、参数、次数、超时和事实来源。

### 7.7 前端展示

涉及文件：

- `mall-ai-web/src/App.vue`
- `mall-ai-web/src/types.ts`
- `mall-ai-service/app/schemas/customer_service.py`

新增公开 DTO（不包含内部 ID）：

```text
task_status:
  active | paused | none
task_label:
  例如“订单异常诊断”
task_hint:
  例如“还可继续：补充订单号后核验物流”
```

交互要求：

1. 在聊天区域上方或侧边展示轻量“已暂存任务”卡片，而非技术术语 `interrupt` 或“待办查询”。
2. 可提供“继续”“放弃”按钮，但按钮只是辅助；自然语言识别是主入口。
3. 不要求用户回复精确关键词“确认”“取消”“继续”。
4. Proposal 卡仍展示确认和暂不提交按钮，但用户可继续问其他问题。

## 8. 一次性数据与兼容性处理

本次为一次性切换，不保留旧/新两套路由并行决策。

发布时的处理规则：

1. 旧 Redis `pending_tool_call`、旧 Durable checkpoint、旧售后 draft/proposal/action 如无法安全映射到 `TaskSnapshot`/`transaction_gate`，直接按过期处理并提示用户重新发起；不要猜测恢复。
2. 已提交到 Java 的售后申请不受影响，仍以 Java 事实查询和状态机为准。
3. 发布前删除或改写旧入口优先级测试，避免测试继续固化“pending 必须抢占消息”的旧行为。
4. 不保留“新 P0 失败时退回旧 pending 优先路由”的 fallback；模型不可用时安全停止本轮，不让旧架构悄悄复活。

## 9. 验收与 EvalCase

必须新增并通过以下合同测试与合成评测：

| 场景 | 预期 |
| --- | --- |
| 等订单号时问退款运费 | 识别为 `temporary_detour`，政策回答成功，订单任务暂停 |
| 政策回答后提供订单号 | 识别为 `resume_paused`，恢复订单诊断 |
| 等订单号时问普通聊天 | 回答聊天，订单任务不丢失 |
| 有 Proposal 时问政策 | 回答政策，Proposal 保留且不被自动提交 |
| 有 Proposal 时说“那就按这个办” | 识别自然确认，提交前仍通过 Java 校验 |
| 有 Proposal 时说“先不用了” | 识别撤回，未产生 Java 写入 |
| active B + paused A，再出现 C | 不静默覆盖 A/B；仅必要时自然澄清 |
| 服务重启后恢复 paused task | 任务摘要和可恢复状态正确保留 |
| 模糊消息同时像 A/B | 模型请求澄清，不按关键词误恢复 |
| 缺订单号 | 产生普通 `waiting_input`，不创建旧式 `interrupt` checkpoint |

至少记录以下指标：

```text
任务关系判断正确率
隐式切题识别率
暂停任务恢复率
错误恢复旧任务率
任务静默覆盖/丢失率
多工具任务完成率
确认意图识别准确率
```

## 10. 交付完成定义

满足以下全部条件才算本次升级完成：

1. 每条新消息先经过任务感知 P0；不存在旧 pending 先抢占消息的路径。
2. 会话中存在真实、可持久化的 `active_task` 与最多一个 `paused_task`。
3. “缺订单号”是普通 Agent 澄清，不再是默认 Durable `interrupt()` 场景。
4. 用户可通过自然语言隐式切题和恢复任务，无需固定命令。
5. Proposal/Action 作为 transaction gate 保留，不阻断其他对话。
6. Agent 可在允许工具范围内自主决定多工具调查步骤。
7. Java 的事实、资格、状态机、幂等和最终写入边界没有弱化。
8. 前端展示“已暂存任务”，不暴露内部任务或 checkpoint 标识。
9. 新增任务切换 EvalCase、受影响 FastAPI 测试、Vue build 和相关 Java 测试全部通过。

## 11. 面试表述

> 我把客服系统从 pending workflow 优先，重构为任务感知 Agent 优先。模型不仅识别业务意图，还结合活动任务和唯一暂停任务判断当前消息是在继续、临时切题还是恢复旧任务。这样用户可以自然地从订单诊断切去问政策，再在之后自动回到原任务。Workflow 没有被删除，而是收缩到事实校验、Proposal、确认和 Java 最终写入等必须确定执行的边界；Agent 则负责语言理解、任务调度和多工具规划。这使系统既不像固定表单，也不会让模型越过交易系统。
