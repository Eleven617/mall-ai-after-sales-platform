# Build 17: Quality Checkpoint Requirements Alignment

## Purpose

Build 17 makes fixed evaluation runs measurable and bounded. It is a
developer/CI checkpoint, not a customer-facing feature and not another Agent.

## Users And Data Visibility

| Audience | Can run it | Can see |
| --- | --- | --- |
| Customer | No | The existing public answer, verified facts, and after-sales workflow only. |
| Developer / CI | Yes, by an explicit script command | Safe case IDs, pass/fail status, elapsed time, model-call count, token totals, failure category, and optional configured cost estimate. |

The checkpoint report must never include a bearer token, member ID, order ID,
raw customer message, raw model response, retrieved policy text, tool payload,
or API key. It writes no customer data and creates no HTTP route, web page, or
reviewer role.

## One Acceptance Flow

1. A developer explicitly runs one fixed checkpoint profile, for example the
   15 reviewed RAG grounding contracts.
2. The runner prints privacy-safe progress after every case and stops before a
   configured total-time or case-count budget is exceeded.
3. A model/network configuration issue is reported as `environment_blocked`;
   a completed case that violates its reviewed contract is `quality_failed`.
4. The customer chat path remains unchanged: a normal Vue request does not
   start this runner and never receives its report fields.

## Non-Goals

- No per-request evaluation, no customer-visible trace/RAG fields, and no
  reviewer/testing website.
- No second answer-generation call or generic narration layer.
- No automatic prompt, policy, threshold, workflow, or code change based on a
  failed checkpoint.
- No production-accuracy, production-cost, or production-SLA claim from local
  results.
- No Build 18 RabbitMQ/Outbox business event work in this batch.

## Model Calls, Cost, Latency, And Failure Behavior

- Scripted Agent and LangGraph profiles use zero provider calls.
- Local retrieval uses the packaged embedding model and makes zero cloud model
  calls.
- The explicit live-grounding profile can call DeepSeek. It records provider
  response usage when available, elapsed milliseconds, retry attempts, and a
  configured optional price estimate. There is no hard-coded provider price.
- Live checkpoints use a stricter per-call timeout and retry cap than normal
  customer traffic. The runner also has a total time and case-count budget.
- A checkpoint failure changes no customer configuration. `environment_blocked`
  means repair the local network/provider configuration and rerun; 
  `quality_failed` means inspect the reviewed case and decide on a human-approved
  regression or code change.

## Rollback

The runtime default measurement sink is a no-op. Removing the explicit script
and checkpoint modules leaves the customer request chain unchanged. No database
or Redis migration is part of Build 17.
