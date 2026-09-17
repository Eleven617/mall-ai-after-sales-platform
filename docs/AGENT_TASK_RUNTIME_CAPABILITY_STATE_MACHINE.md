# Agent Runtime 能力补齐状态与边界

本文件记录本阶段已经实现的服务器边界，不代表在线模型验收或生产部署。

## 售后草案

`created/planning → executing → ready_to_commit(revision N, awaiting_confirmation) →
ready_to_commit(revision N+1, superseded N) → committing → executing/blocked`。

修改只接受当前任务所有者提交的 `proposalRef + revision + applicationType`，由 Runtime
生成新的 proposal、内容哈希和版本；旧版本进入不可确认的 `superseded` 历史。修改不调用
Java、不生成幂等键、不写售后申请。确认前端必须再次携带当前版本；旧版本返回
`stale_proposal_revision`，不会猜测用户意图。过期、撤回、哈希冲突和事实失效均安全停止。

## 人工协同

模型只可提出 `open_human_case`，参数限于当前任务 Artifact 引用与
`tool_failure | insufficient_evidence | manual_review`。服务器为 Proposal 绑定
`commit_human_case`，确认后依据安全 Artifact 类型生成 Diagnosis/Handoff 摘要，调用既有
`register_case_handoff → Java /ai/cases/handoffs`。确认前 Java 案件写入为零；未知结果不自动重放，
同一任务和 Proposal 使用稳定 Case Key 保证幂等。人工案件与售后申请是两种公开状态。

## 澄清与恢复

缺订单号、申请类型或必要证据时只走 `ask_user → waiting_for_user → 同一 task resume`；
不暴露 `request_customer_evidence`，不创建虚假补件异步系统，也不重复已经完成的事实调查。

## 能力目录

- 模型可见：`search_catalog`、`compare_skus`、`read_order`、`read_logistics`、
  `read_inventory`、`retrieve_policy`、`list_service_applications`、`build_service_resolution`、
  `create_after_sales_draft`、`open_human_case`、`search_task_memory`、`spawn_subtask`。
- 服务器内部：`commit_after_sales_action`、`commit_human_case`、`amend_after_sales_draft`。
- Backlog：`request_customer_evidence`、`schedule_follow_up`；当前无真实调度/通知履约链。

## Provider Guard

所有 DeepSeek/OpenAI-compatible HTTP 请求在 `llm_service._post_with_retry` 之前经过
`provider_guard`。默认 `offline/deterministic/replay` 均拒绝；Key 存在不等于授权。正式 live
调用必须同时绑定授权标志、Release ID、Batch ID、Ledger 路径和 40 位 Runtime Commit。
拒绝只记录 `provider_guard` 安全分类，不保存 Prompt、响应、reasoning、Token 或业务标识。
