# 统一图迁移、回退与扩展

本文件描述本次实现及已完成的授权本机验收。AI/Web 已本地切换；尚未提交、推送或远程发布。

## 实现与数据归属

| 实现 | 合同 |
|---|---|
| `app/services/conversation_graph.py` | 每条消息独立 ConversationGraph；只存路由、服务端任务引用、请求摘要哈希和完成标志 |
| `app/services/conversation_memory.py` | ConversationGraph 所有轮次共享的唯一安全记忆仓；同一会话短锁串行写入；交接只读该投影 |
| `app/runtime/task_graph.py` | TaskGraph 是长任务唯一执行器；TaskRuntime 不再保留循环执行器 |
| `app/runtime/task_store.py` | Plan、Artifact、ContextPack、Proposal 领域权威；storage_revision 比较交换；展示 status 可由同修订检查点重建 |
| `app/runtime/graph_checkpoint.py` | 内存测试适配器与官方 MongoDBSaver；只开放最新线程，错误持久化使用固定安全文本 |
| `app/skills/unified_gateway.py` | 统一 Task Skill 与传统工具兼容入口，复用现有 Catalog 与角色校验 |
| `app/runtime/capability_graph.py` | 诊断、售后、政策、运营子图的请求内依赖容器；实际 LangGraph State 仅有 sequence |

持久化版本为 `conversation-v1` / `task-v1`。依赖固定 LangGraph 1.2.14、checkpoint 4.2.0、MongoDBSaver 0.5.1、PyMongo 4.18.3；安装其依赖不改变模型或 RAG 的选择与参数。

### State 和线程

会话执行线程为 `conversation-v1-SHA256(scoped_session,request_id)`；记忆线程使用独立的服务端 `scoped-session` 命名空间。同一请求重复提交不会再次创建/继续任务；重复请求返回原事项查询提示，不持久化或回放原始答案。前端提供随机 request_id，旧客户端未提供时服务器生成；**旧客户端无法获得跨 HTTP 重试去重保证**，Java 幂等仍生效。

TaskGraph State 使用 `TaskCursor` 严格校验：版本、owner_ref、task_ref、domain_revision、next_node、status、model_calls、tool_calls、wait_type、plan_version、artifact_refs、proposal_ref。模型决策在请求内校验；原始参数不保存为可重放决策。

State 另有服务端生成的 run_ref。领域仓保留 graph_invocation_pending 收尾凭据；只有图调用正常结束才清除。即使 SDK 的 pending writes 恢复出完整节点结果，未正常收尾仍先核对并安全暂停，不直接再调用模型。

安全记忆继续使用原有审核词汇投影与 8 条上限，记录角色、来源引用、sequence、显式 task_ref、遗漏/截断标记、revision、expires_at。无法安全投影的内容被标为遗漏；不把旧自由文本摘要搬入新图。现有 Task Context Curator 压缩继续使用原 Prompt 和 Artifact 输入。旧 `ConversationState.recent_messages/summary/handoff_fragments` 不再写入领域仓；handoff_fragments 仅在读取时填充兼容投影。

Mongo 使用独立集合 `orchestration_checkpoints_v1` / `orchestration_writes_v1` / `orchestration_tombstones_v1`。检查点及 pending writes 均有 TTL；任务新记录使用 BSON Date 的 `record_expires_at`，应用读取仍验证领域 TTL。旧数值型过期字段不能假定会被 Mongo TTL 自动清理，旧记录没有批量删除。会话删除清除全部相关轮次与记忆历史，并设置墓碑拒绝迟到写入。

身份验证发生在 HTTP 边界的 Java 调用中。TaskGraph 线程和领域记录双重绑定 owner；request_id、线程 ID、模型返回的 task_ref 都不提供身份权限。凭证仅在本次认证请求内使用，恢复要重新认证。

### 失败与恢复

- `await_input` 节点只有 interrupt，无业务副作用。新的继续输入/确认动作决定恢复分支。
- 模型、只读 Skill、Curator/Critic 调用前先记录预算，进程退出不减少计数。
- 中断发生在非等待节点：恢复只登记 `interrupted_graph_run`，保留领域事实，要求新的交互；不重放丢失的请求内决策。
- 领域已保存、检查点未保存：领域修订保留；不使用旧投影覆盖领域 Proposal 或 Artifact。查询可读取领域结果，下一次认证交互重新登记等待位置。
- Java 成功但响应丢失：Proposal 保持 confirmed/unknown；客户点击“查询原提交结果”，用原幂等键只读查询。未查到结果不自动重新提交。
- 锁冲突返回 409；领域修订冲突不继续调用。读 Mongo、写检查点失败时不能退回另一个可独立推进任务的执行器。

## 旧任务过渡

1. 部署前取得授权，保留卷与旧镜像，记录实际 image revision；通过聚合查询统计旧在途任务，不读取原始会话。
2. 暂停入口接收新变更，等待有界请求结束后切换。**禁止新旧副本同时接收同一任务的变更请求**；旧代码不认识 graph_version，不能指望字段本身阻止旧二进制写入。
3. 旧已完成任务只读保留。缺 graph_version 的在途任务在客户显式继续时登记新版本；旧待确认卡失效，保留已验证事实，新提案需要重新确认。
4. 旧 confirmed/unknown 不重新执行，只能对账。旧传统会话待确认缓存在版本转换时失效；Java 已提交的售后与案件不受影响。
5. 不自动迁移原始 Java 聊天历史。前端展示历史仍归 Java，模型只读取新安全记忆。

聚合入口为 `mall-ai-service/scripts/inspect_graph_migration.py --inspect`。只输出图版本、状态、数量和最早到期时间。本轮部署前已对运行中 Mongo 执行等价的版本/状态/数量聚合，保留全部旧数据；数量见环境记录。

## 回退

回退首先停止新图入口并等当前有界请求结束，保留 Mongo/Redis/Java 数据与当前镜像。没有实现“把新图待确认任务降级为旧执行器任务”的转换，不能直接让旧版本接手这些任务。

安全回退选择是恢复上一镜像的只读入口，并保持任务变更入口关闭，直到新图问题修复；或在确认所有新图在途任务已安全结束/失效且未知提交完成 Java 对账后，才恢复旧变更入口。不得清卷、重置数据库、覆盖历史 Ledger、复活旧确认卡。真实切换和回退演练尚待授权。

## 新增 Skill / 子图

1. 先写版本化输入输出 Schema、角色、读写模式、预算、超时和幂等/对账合同。
2. 在现有 Catalog 登记能力；兼容工具名只能由网关映射，不让模型选择执行器或网关实现。
3. 读取通过统一网关，返回安全 Artifact；写能力只产生 Proposal，由显式确认节点重新核验并提交 Java。
4. 子图把客户消息、HTTP 客户端与凭证放在请求内依赖里；State 只能包含审核通过的引用/游标。不得直接给子图安装第二套会话记忆。
5. 如果新增可恢复副作用，先定义调用前记录、幂等键、结果未知与只读对账，再决定节点边界。不能把整个旧循环塞进单个图节点。
6. 新增成功、拒绝、跨身份、重启、重复请求、预算及存储部分失败测试，并在功能矩阵记录实际证据。改图主版本必须同时更新旧数据拒绝/过渡策略。

## 本轮执行与复现

已授权并执行真实 Mongo 索引/TTL、跨进程恢复、Redis 并发锁、旧数据只读聚合、Java 成功后丢响应对账与浏览器路径。原 18 条迁移合同仍为内存/脚本测试；新的环境证据单独保存，不能混为一次执行。

- `verify_graph_persistence.py`：在关闭模型的 AI 容器中，使用唯一 `mall_graph_acceptance_*` 数据库运行 prepare；重启 AI 后运行 recover。检验实际 Mongo 及 Redis，无 Java 写入。
- `verify_graph_java_recovery.py`：宿主运行，创建专用合成客户/订单，子进程以 stdin 接收临时凭证。真实 Java 提交后注入丢响应，重启 AI，只查原 key；随后运行会话能力验收。
- `verify_handoff_upgrade_live.py --offline-worker --browser --restart --graph-capabilities`：专用合成身份，通过 Java 完成人工闭环；模型 worker 必须关闭。
- `run_real_local_showcase.py`：限定 deterministic，执行主链和暂停恢复场景。报告及截图为本次环境证据，不是 live 模型演示。
- `archive_langgraph_evidence.py`：归档安全报告，计算脚本和工件哈希，构造具名验收矩阵；不会调用模型或执行业务动作。

本次临时 Compose override 为 `tmp/langgraph-acceptance.compose.yml`：deterministic、live auth=0、Key 置空、两个模型 worker 开关均关闭。该文件是本机验收配置，不应覆盖正常运行配置或提交密钥。恢复外部模型须另获授权。

回退旧镜像的只读运行窗口、生产备份恢复和外部模型质量未演练。保留旧镜像不等于回退验收通过；禁止将旧二进制直接接管新图在途确认。
