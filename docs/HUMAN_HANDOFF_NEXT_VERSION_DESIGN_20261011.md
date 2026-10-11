# 下一版：客户转人工、人工售后与运营问题分析设计

日期：2026-10-11。状态：需求与实现建议稿，供用户对齐和实现 AI 执行；不是已实现或已验收报告。

本次只新增设计与学习文档，不修改业务代码、不运行测试或模型。本文中的新接口、字段、阈值、保留期都是下一版提案。实施前对照当前工作区复核，不把文档当成当前行为。

## 1. 产品目标与本次边界

目标：客户在任何受支持的商城服务中都能明确请求人工；系统携带必要且脱敏的任务背景创建人工售后案件；运营人员分析客户为何要求人工、哪些问题重复出现；开发或业务人员得到可核验的改进线索。

三个使用者各有独立界面和权限：

- 客户：请求人工、确认交接、查看排队/处理状态、补充必要信息。
- 人工售后处理人员：领取案件、理解背景、核验业务事实、补件、解决与结案。
- 运营分析人员：查看脱敏案例、分类趋势和人工确认原因；创建内部改进事项，不直接操作客户订单或代替客服处理案件。
- 质量/开发人员：在授权范围内查看脱敏技术事件和改进事项，不自动获得客户聊天或商城写权限。

不把人工案件等同于退货退款申请。政策咨询也可以有人工案件，但不应因此自动创建退款、维修或换货申请。人工已领取也不代表业务申请已获批准。

本期不接第三方坐席实时聊天、不自动执行退款、不自动向外部工单/邮件系统发送内容、不让模型自行修改代码、不建设通用数据仓库。客户看到“已转人工”意味着本站案件已入队，不意味着实时客服已经接通。

## 2. 当前实现基线：必须保留的事实

以下为工作区静态核对，不代表运行容器与源码版本一致，也不是生产运行证明。

| 当前路径 | 已核实行为 |
|---|---|
| Vue 当前聊天入口 | App.vue 传 unified_entry=true，进入 conversation_entry.handle_unified_message |
| 统一会话路由 | 结构化模型选择 answer/start_task/continue_task/clarify；answer 才委托原有 handle_customer_message |
| 原有诊断路径 | agent 路由进入只读调查；_build_diagnosis 根据工具结果生成分类和 handoff；外层登记条件要求诊断、handoff、已核验事实与认证凭证 |
| TaskRuntime 人工路径 | open_human_case 形成待确认提案；确认执行 commit_human_case，经 commerce_gateway._commit_human_case 调用 register_case_handoff |
| 两条路径的差别 | TaskRuntime 路径校验 Artifact 引用等条件；不能把原有诊断外层的 verified_facts 条件当成所有入口共享的条件 |
| Java 登记 | AiCaseHandoffServiceImpl 在事务中创建/复用 ai_case_handoff，并确保 ai_service_case 排队案件及其 Outbox 存在 |
| 人工处理 | 已有队列权限、领取、版本条件更新、动作幂等、审计和 Outbox；支持核验、补件、处理、结案 |
| 运营列表 | 读取 ai_case_handoff 的最小字段；按时间倒序，最多 50 条；当前列表不随 7/30 天窗口过滤 |
| 运营统计 | Java 查询售后、Outbox、消息交付、转人工分类；窗口内转人工按 member_id + case_key 去重 |
| 运营模型分析 | 输入单条分类摘要和聚合指标，输出草稿；未核实具有逐条事实语义核验能力 |

主要缺口：客户主动请求与系统建议未统一清晰表达；任务进展和客户诉求材料过少；原因分类混合业务类别、系统状态与人工原因；运营列表与统计口径不一致；改进事项没有完整闭环。

不能宣称当前完全没有客户主动人工路径，也不能宣称只有旧诊断能进入人工案件。

## 3. 新版触发规则：什么时候建议、什么时候真正创建

### 3.1 两个明确入口

1. 客户页面常驻“转人工”入口：点击表达客户意愿，服务端生成交接预览卡，不依赖模型服务可用。
2. 自然语言：“我要人工”“找客服帮我处理”等，由结构化入口识别转人工意愿；出现“人工”一词不等于提出请求，例如“转人工需要多久”是咨询。模型只提出意图，不直接建案。

复杂调查、单项物流查询、政策咨询、售后申请处理中均可请求人工。没有订单号或没有已核验订单事实，不得阻止政策咨询等一般人工请求。需客户登录才能形成有归属的案件；未登录先引导登录，不显示已登记。

多任务场景：当前页面明确选中的任务由服务端验证后关联；客户明确指向某任务则验证归属；无法确定时显示任务选择或“一般咨询”，不猜测关联，不要求用户填写内部任务 ID。

### 3.2 确认与写入的一致规则

本版设计统一采用“交接卡 + 明确确认”后建案，复用当前版本化提案机制。客户说“转人工”或点击入口后立即出现卡，不再进行订单诊断或反复询问原因。

卡片显示：待交接目标、可选原因、所关联事项、将提交的脱敏摘要、按钮“确认转人工”。不把原始聊天、内部标识或技术事件展示为操作参数。

这样保留现有 owner/version/TTL/content hash/confirmation 约束。若以后要把一次口头请求直接当作某个版本的提交确认，必须另行设计，不允许实现 AI 偷跳提案校验。确认原因可选，用户不填也能提交。

提案内容变更后必须产生新版本；已过期重新生成。模型分析尚未完成不阻碍提交基本交接包。

### 3.3 系统提出建议的明确条件

系统可以显示“需要人工帮助吗”，但不自动创建案件。建议事件与客户主动请求分开记录。

初版采用版本化、可配置规则：

- 受控工具重试已耗尽，仍无法完成用户目标。
- 针对明确的问题完成政策检索后无足够证据。
- 系统明确不支持该能力，或业务规则规定必须人工判断。
- 同一任务同一必要信息项已追问两次仍无法推进；仅能证明追问次数，不能证明客户已正确提供。

单次可恢复错误、订单运输中、客户信息尚未提供，均不能单独作为自动建案条件。是否显示建议应根据可验证的任务进展判断，不依据模型情绪猜测。

### 3.4 决策矩阵

| 输入/事件 | 用户可见行为 | 是否建案 | 来源 |
|---|---|---|---|
| 客户说“转人工” | 立即出交接卡 | 确认后 | customer_requested |
| 点击转人工按钮 | 同上，模型不可用也可操作 | 确认后 | customer_requested |
| “转人工需要收费吗” | 回答规则，不误建案 | 否 | 无 |
| 系统建议，客户未接受 | 保留建议，不计实际交接 | 否 | system_suggested |
| 客户接受系统建议 | 出卡/确认同一交接 | 确认后 | system_suggested_accepted |
| 普通政策没检索到 | 明确证据不足，并提供人工入口 | 确认后 | 根据实际选择记录 |
| 已有同一未结束案件，又要求人工 | 返回已有案件状态并允许补充 | 不新建 | 记录重复表达事件 |
| 新问题，与已有案件不同 | 选择新事项/一般咨询 | 确认后新建 | customer_requested |
| 未登录 | 登录引导 | 否 | 不伪造成功 |

## 4. 一次交接完整实例

合成示例：客户办理维修时说“我已经填过了，怎么还问，转人工”。

1. 入口识别请求，或客户点击按钮。服务器记录请求事件并生成交接预览，不运行完整订单调查才能放行。
2. 服务端读取当前任务的受控投影：目标=维修，阶段=信息收集，已完成=识别诉求，未解决=必要信息尚未被接受。
3. 客户诉求摘要为“客户认为信息被重复索要，希望人工继续”；明确它是客户陈述。若没有可安全摘要的内容，只记录“客户请求人工”。
4. 程序事件记录实际追问次数，若没有事件证据则标 unknown，不填写猜测次数。
5. 客户确认卡；Python 提交 Java。Java 在一个本地事务中保存交接、人工案件、初始动作审计和 Outbox；返回 opaque case_ref、状态和版本。
6. 前端展示“已登记，等待人工领取”。原任务标 waiting_human；禁止原任务继续自动提交已交接范围的业务动作，但允许其他独立任务和只读查询。
7. 后台分析任务读取受控包，生成“重复追问”初判。失败时案件仍能领取。
8. 人工领取、核验后可确认或改分类，例如确认实际是信息格式不合法，而不是上下文丢失。
9. 运营统计该事项的客户请求来源、业务类别、初判与人工确认原因。开发改进条目只标“待核验根因”，不把初判当成故障事实。

## 5. 交接数据契约与脱敏规则

所有引用须不可推导内部业务标识，读取时仍检查角色、归属和范围。客户、运营、人工处理、开发分别提供 DTO，不用同一个完整对象切换显示。

| 信息 | 字段建议 | 来源/限制 |
|---|---|---|
| 唯一交接 | handoff_ref、case_ref、schema_version | Java 生成；不要将数据库自增 ID 暴露到页面 |
| 来源 | trigger_source、entry_channel | 服务端记录，不允许模型改写；channel 为 chat/button/legacy |
| 请求时间 | requested_at、suggested_at、confirmed_at | 服务端时间，未知为空 |
| 任务关联 | conversation_ref、task_ref、task_version、application_ref | 全部可空但须验证归属；无任务也可转人工；一般咨询无需假建订单任务 |
| 业务类别 | business_topic | logistics/policy/refund/return/exchange/repair/application_follow_up/general/unknown |
| 任务快照 | goal_summary、stage、completed_steps、open_issue | 受控脱敏投影；目标<=200字，未解决问题<=300字，完成步骤最多5项 |
| 客户诉求 | customer_reason_summary、customer_selected_reason | 摘要<=300字，非原话；客户自行选择与模型判断分开 |
| 系统证据 | evidence_refs、tool_error_codes、asked_field_counts、elapsed_ms | 只存允许的事件、计数、错误枚举；没有就 unknown/null |
| 分类 | primary_reason、secondary_reasons、classification_source、review_status | 次要标签最多2项；来源 customer/model/rule/human/unknown |
| 分析版本 | analysis_version、taxonomy_version、prompt_version、model_version、input_projection_hash | 用于复现和比较，不存 Prompt/思维链/原始模型输出 |
| 处理结果 | case_state、claimed_at、resolved_at、closed_at、resolution_code | 来自 Java 人工案件状态，不让模型填写事实 |
| 人工修正 | verified_reason、verification_note、reviewer_ref、reviewed_at | 角色受控；保留旧分析版本，不覆盖审计历史 |

禁止入运营数据集：原始客户对话、姓名、电话、地址、完整订单号、Token、完整工具载荷、RAG 原文、Prompt、思维链。模型输入仅使用允许的 Artifact/会话投影；不得把原始聊天复制进 Trace 或新表。

需要理解客户表达时，先在现有授权服务内选择与本次交接有关的少量内容并脱敏，生成允许字段。默认最多最近6条相关消息、且仅允许投影总量不超过3000字符；这是新策略，不是当前事实。超范围截断需写 limitation，不靠长文本兜塞字段。脱敏失败则省略自由文本，只用结构化事实登记。

仅靠手机号正则或 Pydantic 字段长度不构成完整脱敏：使用允许字段、实体识别/替换、输出检查和合成敏感样本测试。客户可预览的摘要与仅开发可读的技术引用分开。自动摘要不能声称已经核实客户的陈述。

## 6. 分类方法：业务、转人工原因、技术根因分开

主原因候选：human_preference、intent_misunderstood、repeated_questions、answer_or_evidence_insufficient、tool_or_system_error、capability_or_permission_limit、business_dispute、delay_or_complex_process、unspecified。

- business_topic 描述客户要办什么，如维修。
- primary_reason 描述为什么转人工，如反复追问。
- technical_root_cause 是后续授权开发核实的原因，如版本切换漏更新字段；初始必须 unknown，不让模型直接认定。
- 现有 diagnosis_category/evidence_status 保留为 legacy_diagnostic_labels，不再充当运营全部分类维度。
- 客户明确选择的原因、程序观测、模型推测、人工核实四者分别留来源。模型不能覆盖客户陈述或人工最终分类。
- 以枚举与语义验证约束输出；无证据不能填具体根因。模型给的 confidence 不是概率准确率，不用于自动升级权限或承诺事实。

分析例：程序只证明同一字段追问了3次，客户说已提供；模型可初判 repeated_questions，并写“需核验字段接收与更新”。不得写“Redis 丢失导致客户失败”。

## 7. 存储与系统边界

复用 Java/MySQL 的 ai_service_case 作为人工案件权威，不另建一套人工状态机。复用 ai_service_case_action、ai_service_case_outbox、已有 Publisher/Receiver 和角色权限。

新增可审计迁移，建议三类数据：

1. ai_handoff_record：每次成功交接的来源、业务分类、任务关联与脱敏快照，唯一关联 case_ref；revision 用于补充版本。
2. ai_handoff_event：requested/suggested/confirmed/reused/cancelled 等事件及幂等标识；正文不含对话；用于漏斗统计。建案成功的 confirmed 事件必须与案件同事务写入。
3. ai_handoff_analysis：输入版本、分类草稿、证据引用、分析状态、人工复核信息；按 handoff_ref + snapshot_version + analysis_version 唯一。

新增内部改进事项表 ai_operations_improvement：问题说明、脱敏证据引用、归属团队、状态、验证方法、结果；所有变更通过 Admin 的权限、版本和审计边界。

标量分类/时间/状态用可索引列；受限步骤列表和引用可用 MySQL JSON，应用严格校验尺寸。不得保存任意工具 JSON。MySQL 5.7 兼容，别依赖新版本 CHECK 约束代替服务端校验。

TaskRuntime 的任务/Artifact 继续使用现有独立存储；Java 只接收允许的交接投影。Python 不直连商城 MySQL。Mongo 任务更新与 Java 事务之间不建立虚假的跨库原子事务：Java 已成功但任务同步失败时，依靠稳定请求引用查询对账恢复。

## 8. API 与可靠执行契约（新接口命名建议）

| 调用 | 职责 |
|---|---|
| Vue -> FastAPI POST /human-handoffs/prepare | 传会话/任务 opaque reference 和可选原因；验证归属，服务端生成提案预览；按钮路径无需模型 |
| Vue -> FastAPI POST /human-handoffs/{proposal_ref}/confirm | 带版本、内容哈希与确认；沿用同一 Runtime 确认服务，不能另开跳过 ActionProposal 的写入口 |
| FastAPI -> Java POST /ai/human-handoffs | 客户身份 + 受控服务认证；写交接、人工案件、动作审计、Outbox |
| FastAPI -> Java GET /ai/human-handoffs/by-request/{request_ref} | 客户归属校验；超时后的只读结果确认 |
| Vue -> FastAPI -> Java 查询人工状态/补件 | 复用现有案件公开 DTO、版本与幂等规则 |
| 分析 Worker -> Java 内部分析读写接口 | 短期受限服务身份；只读脱敏包、写分析版本，不得重用过期客户 JWT，不具备建案/退款权限 |
| 运营 Vue -> FastAPI -> Admin /ai/operations/handoffs | 分页、时间、来源、业务与原因筛选；使用同一筛选口径返回统计 |

prepare 没有任务时生成轻量的服务端交接意图对象/提案，不伪造订单 Artifact。扩展受控上下文 Artifact 类型 conversation_context_projection，允许无订单事实的咨询；校验 owner、version、TTL、内容哈希。原 skill schema、Runtime allow-list 和 Java 入参一起升级，不是删除旧校验即可。

幂等：request_ref 在首次 prepare 时固定；网络重试必须复用。Java 对 member + request_ref 唯一约束，同请求不同内容返回冲突。另用 server-owned active_scope_key 防止同一客户同一事项并发创建两个未结束案件，只有结束时释放；不能用模型分类作为唯一去重键，因为分类会变化。无任务的一般咨询用服务端交接 episode 引用；客户可明确开启不同事项。

Java 写入超时：界面显示结果待确认，先按原 request_ref 查询（例如1、2、4秒间隔，最多3次）。短时间未查到不能断言失败；只有Java幂等契约通过测试后才允许同键有限重提（最多1次），不能换键新建。仍未知则保留待确认并让后续刷新继续查询，不能显示“已成功”或悄悄无限重试。

Java 事务完成后由 Outbox 发布 handoff_created；分析消费者只接收引用及版本，重新获取受控包。消费者通过分析唯一键、领取租约和条件写入避免重复保存，过期重领可重算但不得重复业务动作。旧输入版本结果拒绝覆盖新版本。

模型调用成功但结果落库前进程崩溃，仍可能重复产生模型成本，不能承诺外部调用 exactly-once。分析最多2次生成尝试，单次超时30秒、输出上限800 tokens、每案分析总输入预算上限6000 tokens（重试也计入），网关纠正计入次数。没有配置或预算不足则标 unavailable。精确策略实现时经合成评测确认，不把这些预算写成当前性能结果。

## 9. 状态、人工处理与运营各自何时更新

交接提案：PREPARED -> CONFIRMED / EXPIRED / CANCELLED；结果未知是客户端提交状态，不擅自把 Java 案件标失败。

人工案件复用当前状态：QUEUED -> CLAIMED -> IN_REVIEW -> RESOLVED -> CLOSED；补件走 AWAITING_CUSTOMER_INFORMATION，重新开启沿用既有校验。补充资料不能悄悄新建案件。

分析独立状态：PENDING -> RUNNING -> SUCCEEDED / FAILED / UNAVAILABLE；分析失败不回滚案件，人工领取不等待模型。

普通案件关闭不会自动意味着退款完成。若需真实退款等业务动作，继续走 Java 原有业务权限、资格、确认和事务。人工关闭时填写结果代码与原因确认；事实不足可选择 unresolved/unknown，不强迫编造根因。

原任务交接后保存 case_ref 和 last_synced_version。历史待确认业务提案设为不可直接执行，客户若需要再次自动办理必须重新核验生成新版本，避免人工与 Agent 同时改变同一事项。已提交且结果未知的业务动作先对账，不能当作未执行。

## 10. 运营页面与统计口径

页面按三层组织：

- 概览：实际交接数、客户主动占比、系统建议接受数、主要转人工原因、待领取与已处理数量。
- 案例：同一筛选条件下的分页列表；详情展示脱敏客户诉求、目标与进展、程序事实、初判、人工结论和版本。
- 改进：某问题的发生数量、代表案例引用、责任团队、待核实原因、验证计划、改动后同口径数据。

统一使用业务时区 Asia/Shanghai 展示、服务端规范化时间存储，查询边界 [start,end)。默认7/30天窗口，但列表、总数和分类使用同一过滤条件。所有交接数按 case_ref 去重。页面区分“当前页20条”和“筛选总数”，不再把最多50条列表长度当全部统计。

| 指标 | 明确口径 |
|---|---|
| 转人工请求次数 | 去重后的 requested 事件；HTTP 重试不增加，新的客户表达可增加 |
| 实际交接数 | confirmed_at 在窗口内、Java建案成功的 distinct case_ref |
| 建议接受数 | 来源 system_suggested_accepted 的成功交接 |
| 来源/原因占比 | 所选窗口实际交接数为分母；unknown保留，不丢弃以提高比例 |
| 当前待处理 | 当前状态的存量，需要标明是全量存量还是该窗口建案队列的存量 |
| 首次领取时间 | claimed_at - confirmed_at；未领取单列；无历史时间不补造 |
| 处理完成时间 | resolved_at - confirmed_at，说明是否包含客户等待时间 |
| 转人工率 | 本期仅在完整服务会话分母事件已实现时提供，否则只展示数量，不伪造比例 |

业务分类统计、原因统计与技术健康统计分区。Outbox PUBLISHED/事件 DELIVERED 必须称“消息发布/事件处理”，不能标“配送”。模型不能决定统计 SQL、分母和窗口。

单案摘要分析与整体趋势分析分开按钮/结果。整体趋势分析接收Java聚合及有限、可说明抽样方式的代表案例；必须标样本覆盖和未知原因占比，不能只拿一条案例推断全局。先展示数字和已有分析缓存，新增模型分析异步展示进度，不阻塞页面读取。

## 11. 人工修正、开发排查、保留期

运营可提出“重复追问问题”改进事项，人工售后可修正交接原因，开发只能在授权范围核验技术根因。分别审计，不让运营角色直接领取/退款。内部改进状态为 OPEN/TRIAGED/IN_PROGRESS/VERIFYING/CLOSED；关闭需验证说明，不能仅因代码合并自动称效果改善。

拟议保留策略：活跃案件不自动删；关闭满90天清除交接自由文本摘要和可识别关联投影，最多保留365天的去标识分类事件用于统计。其余业务审计遵守原系统保留策略；不得顺带删除订单、退款、现有聊天或人工案件审计。上述为工程建议，不是法律期限；作为显式配置并在上线前确认适用要求。

实现专门清理任务：分批、可重试、先dry-run、检查案件是否重开/保留标记、记录去标识清理审计；7/30天筛选不删除数据。清理后引用返回已过保留期而不是误报不存在；含自由文本的分析副本一起清理，防止只删原摘要却留下模型复述。

## 12. 兼容与迁移

- 原有诊断自动登记改为建议交接并等待确认；保留诊断能力，不再把生成 handoff 对象等同于建案成功。
- 统一入口 start_task/continue_task 与常驻按钮都使用相同提案、提交服务。原 TaskRuntime commit_human_case 迁移到新契约，不继续伪装成 customer_diagnosis 来源。
- 已有 ai_service_case 保留状态、处理人、审计、事件与 case_id；新投影关联它，不复制案件。
- 已有 ai_case_handoff 在新版视图中标 legacy、来源未知/原有机制、客户动机未知。不能从粗分类回填“客户因不满意而转人工”。
- 切换日期与 schema/taxonomy 版本可筛选。历史演示数据不得宣称真实客户效果。旧字段矛盾展示需复核，不自动篡改历史记录。
- 迁移脚本必须新增、幂等、保留卷；既有脏改动保持。单一新建案路径切换，禁止旧自动写与新确认写并行双建案。
- 回退时关闭新版交接提交，保留查询和已建案件处理；不要回退数据库内容或自动恢复旧的无确认写入。

## 13. 分阶段实现与验收交付

优先顺序按依赖，不承诺一天全部完成。

P0：合成场景、接口Schema、角色矩阵、迁移和基础数据约束。提交新旧契约对照；明确当前工作区与容器版本。

P1：客户按钮/自然语言意图->交接卡->Java建案->人工领取闭环。模型不可用时按钮路径仍可用。所有入口实现共同幂等、超时查询和任务同步。

P2：受控上下文包、异步分类、人工修正、分析状态。先合成固定模型响应验证，再在单独授权后做真实模型评测。

P3：统一窗口分页统计、案例详情、内部改进事项、历史标签和保留任务。

P4：跨入口、跨角色、重启、重复投递、未知结果现场验收。交付截图、接口断言、合成caseId、fixture hash、版本和限制，不用离线测试代替真实现场结果。

| 合成验收场景 | 必须观察到的结果 |
|---|---|
| 纯政策咨询主动要求人工，无订单 | 可确认建案，不要求虚构订单事实 |
| 模型不可用，客户点击按钮 | 可形成基本交接卡并创建案件；原因可unknown |
| 客户询问“人工服务时间” | 不误建案 |
| 系统建议、客户未接受 | 有建议事件，无案件，不计实际转人工 |
| 两次确认/两个并发请求 | 同一案件，动作与Outbox不重复 |
| Java提交成功但响应丢失 | 原请求查询找到同一案件，不换键创建 |
| 客户跨账号引用任务/案件 | 拒绝，数据不泄露 |
| 两个活动任务、客户含糊说“转人工” | 选择事项/一般咨询，不猜关联 |
| 无法安全脱敏文本 | 省略文本、基本交接成功、限制说明清晰 |
| 模型分类失败/重启重投 | 人工案件正常可领取；分析有独立失败状态 |
| 人工修正初判 | 旧版本可追溯，运营按明确口径统计确认原因 |
| 7/30天、时区边界、历史数据 | 列表总数与统计口径一致，legacy明确标识 |
| 队列DELIVERED | 页面显示事件处理，不显示物流送达 |
| 任务同步失败/旧业务提案点击 | 可对账，不重复业务写入；旧提案拒绝执行 |
| 清理后重新访问/案件重开 | 正确显示投影已清理；活跃记录不误删 |

实现 AI 必须遵守 AGENTS.md 的测试门槛；新增模型调用先记录可见性、验收路径、成本/延迟与失败行为。未经单独授权不进行付费模型调用、对外消息发送或发布。修改代码的权限来自用户交给实现 AI 的明确任务，不来自本学习文档。

## 14. 交给实现 AI 的任务说明

请以本文为下一版需求与实现建议，先审计实际工作区及AGENTS.md，保留已有无关改动。重点复用现有人工案件、权限、提案确认、Java事务、Outbox与人工工作台；实现客户主动转人工、受控交接包、异步分类、统一运营口径与内部改进事项。不要仅改名或新增一段Prompt就宣称完成。遇到与当前业务契约冲突的地方先给出具体差异和可审查方案，不静默放宽写权限。按P0-P4提交阶段结果，分别说明实际实现、测试证据、未完成能力及现场验证限制。不要把本文设计或模型草稿当成已上线事实。

## 15. 核对源码入口

- mall-ai-web/src/App.vue、OperationsPanel.vue、ServiceOperationsPanel.vue。
- mall-ai-service/app/services/conversation_entry.py、customer_service.py、intent_service.py、diagnosis_agent.py、case_handoff_service.py。
- mall-ai-service/app/runtime/task_runtime.py、app/skills/catalog.py、app/skills/commerce_gateway.py、app/routers/agent_tasks.py。
- mall-ai-service/app/services/operations_agent.py、operations_client.py、app/schemas/operations.py。
- mall2/mall-portal/src/main/java/com/macro/mall/portal/service/impl/AiCaseHandoffServiceImpl.java。
- mall2/mall-admin/src/main/java/com/macro/mall/serviceoperations/service/impl/AiServiceOperationsServiceImpl.java。
- mall2/mall-admin/src/main/resources/dao/AiOperationsDao.xml。
- mall2/document/sql/migrations/V20260818__ai_case_handoff.sql、V20260831__ai_service_case_collaboration.sql。
