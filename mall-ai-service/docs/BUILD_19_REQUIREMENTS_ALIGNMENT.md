# Build 19 Requirements Alignment: Controlled Multi-Agent Collaboration

**Status:** Build 19 customer/operations collaboration and Build 19.2 are built,
unit-tested and locally Docker-verified. Build 19 Phase B (the independent AI
quality-evaluation Agent and developer page) was additionally built and
browser-proxy verified on 2026-08-20; see
`docs/BUILD_19_QUALITY_EVALUATION_AGENT.md`. A local `订单管理员` test account
was created for the authorized operations path; the separate visual click-through
is presentation evidence, not a substitute for the API and contract checks below.

This document records the agreed scope before code changes. Build 19 is a
controlled collaboration between three separately bounded roles. It is not a
generic Agent swarm and it does not let an LLM decide identity, widen a data
scope, grant a tool, or perform a business write.

## Problem and user-visible outcome

The existing customer diagnosis Agent can safely diagnose an authenticated
customer's order/after-sales problem, but it has no durable, privacy-minimal
handoff to a separately authorized operations role. The existing offline
evaluation utilities also do not yet evaluate a cross-role handoff contract.

Build 19 adds the following real path:

```text
Customer Diagnosis Agent
  -> only when its existing safe diagnosis reaches a human-handoff outcome
  -> server creates a minimum CaseHandoff through Java under the member JWT
  -> an authenticated order administrator opens the internal operations view
  -> Operations Analysis Agent reads only Java-approved aggregate metrics
  -> it returns an internal analysis draft, never a business mutation

Synthetic cases + privacy-safe trace metadata
  -> Offline Critic (development / CI / explicit run only)
  -> contract and regression recommendations, never automatic changes
```

Customers continue to see only the current public customer response, verified
fact cards, return workflow, and a customer-safe human-follow-up message. They
never see a case identifier, agent profile, internal handoff, aggregation,
model prompt, tool trace, source record, operator identity, or Critic result.

## Identity, data visibility, and authorization

The current Java source has separate authentication authorities:

- `mall-portal` authenticates customers through member JWTs.
- `mall-admin` has real Java administrator accounts and roles, including
  `订单管理员` and `超级管理员`, and is now started only as an internal Compose
  dependency.

Build 19 will start `mall-admin` only as an internal Compose dependency and
will add a narrow operations API to it. FastAPI must validate an operator
Bearer token by calling that Java authority; it must not decode the token,
trust a browser role field, or treat a customer token as an operator token.

Only `订单管理员` and `超级管理员` obtain the `operations_analysis` capability.
`商品管理员`, unauthenticated callers, and customer/member tokens are denied.
The administrator source is used as a real role boundary, not as a prompt
label.

## Role capability contracts

| Role | Approved data scope | Allowed tools / steps | Output | Writes |
|---|---|---|---|---|
| Customer Diagnosis Agent | Current Java-authenticated customer's existing order, logistics, policy evidence, and conversation state | Existing read-only customer tools; existing diagnosis budget | Existing public response and, when needed, a server-derived CaseHandoff request | Only the pre-existing deterministic return workflow after explicit customer confirmation; no new free write |
| Operations Analysis Agent | One privacy-minimal CaseHandoff and Java-derived aggregate after-sales metrics | `read_case_handoff`, `read_after_sales_metrics`; at most one approved aggregate query and two model calls | Internal structured analysis draft: facts, risk flags, recommended human attention, limitations | None |
| Offline Critic | Synthetic cases and allow-listed trace metadata only | Offline contract/evaluation helpers; optional bounded model review only in an explicit checkpoint | Private evaluation report and proposed test/regression ideas | None |

The Operations and Critic roles must never receive a customer Bearer token,
raw chat text, phone number, address, payment data, full order number,
customer name, raw RAG chunk, LLM prompt, or Java tool payload.

## Minimum CaseHandoff contract

The durable Java record may retain server-only membership linkage for
authorization and deduplication. The Operations Agent input and operations
view receive only the following allowed fields:

- opaque `case_id`;
- normalized diagnosis category and evidence state;
- handoff reason enum;
- whether human review is required;
- lifecycle status and timestamps;
- schema version and non-sensitive source-flow label.

The server derives a stable, non-browser handoff key from the scoped
conversation and normalized handoff category. The Java table enforces
member-scoped deduplication so repeated customer messages do not create an
unbounded stream of identical cases.

## Operations data and one acceptance flow

The operations aggregate is limited to real fields already held by the local
mall database: after-sales state counts, normalized reason counts, time-window
counts, and Outbox/delivery state counts. It contains no per-customer row or
personal details. Any supplier, warehouse, quality-inspection, SMS, mail, or
refund data is explicitly absent rather than invented.

```text
Customer A is signed in and receives a safe diagnosis that requires human follow-up
  -> FastAPI sends the minimum handoff to Java using Customer A's existing JWT
  -> Java derives the member and persistently deduplicates the case
  -> Customer A sees no internal case metadata
  -> an order administrator signs in through the internal operations panel
  -> FastAPI verifies the admin token with mall-admin and reads one safe case
  -> Operations Agent queries bounded aggregate metrics and returns an internal draft
  -> a customer token, product-admin token, and unrelated operator request are rejected
```

The internal operations panel is a genuine authorized business surface. It is
not the withdrawn Build 15 reviewer/tester UI and it will not expose debug
traces or per-request RAG internals.

## Model cost, latency, and fallback

- Customer requests add **zero** new model calls. The CaseHandoff is derived
  from the existing trusted diagnosis result after an already-existing human
  handoff decision.
- A manually initiated operations analysis can use at most two bounded
  DeepSeek calls: one strict query-plan selection and one strict analysis
  draft. It never runs automatically for every customer request.
- The Offline Critic is absent from customer/operations request paths. An
  explicit development or CI run uses the existing bounded checkpoint policy;
  any optional model call has a recorded time and retry budget.
- If Java aggregation is unavailable, model output fails its schema contract,
  or the model provider fails, the operations UI shows only a safe unavailable
  state. It does not fabricate an analysis and it does not change business
  data.

## Explicit non-goals

- No generic autonomous swarm, role selection by an LLM, MCP server,
  LangChain migration, or Skill loader.
- No automatic approval, refund, order change, return-status change, prompt
  change, policy change, knowledge-base mutation, or code mutation.
- No new customer-visible RAG sources, tool traces, operations data, Critic
  report, Token, admin role, or CaseHandoff identifier.
- No fictional downstream notification, warehouse, carrier, supplier, or
  quality-inspection integration.
- No claim of production-scale availability, model accuracy, automatic
  self-improvement, or a complete human workbench.

## Verification required before completion

1. Java tests: authenticated customer handoff creation/deduplication;
   administrator-role authorization; product-admin/customer denial; aggregate
   DTO has no personal fields.
2. Python tests: capability profiles are independent; CaseHandoff excludes
   raw input/token/PII; operator client validates Java responses; Operations
   Agent accepts only approved data and bounded tools; Critic remains offline
   and non-mutating.
3. API contract tests: public customer DTO remains free of all internal fields;
   operations endpoints reject member tokens and insufficient administrator
   roles.
4. Vue production build and an internal operations-page role check.
5. Docker acceptance: customer handoff -> Java persistence -> authorized
   operator analysis; cross-role and cross-account denial; all services
   healthy. A live model test is optional but, if run, is recorded separately
   from deterministic contract tests.

## Pre-change recovery snapshot

Before Build 19 edits, relevant source, tests, docs, Compose, and migrations
were copied to:

`C:\\Users\\12969\\Desktop\\mall\\tmp\\build19-prechange-20260818`

This recovery snapshot is reference material and does not replace tests.

## Construction and verification result (2026-08-18)

Implemented boundaries:

- `mall-portal` persists a member-scoped, deduplicated `ai_case_handoff` record
  from an existing human-handoff diagnosis. The customer response remains the
  public DTO and does not contain the handoff identifier or key.
- `mall-admin` exposes a read-only operations surface. It independently checks
  the Java role on every request and projects only normalized handoff metadata
  and aggregate after-sales/outbox/delivery counts.
- FastAPI uses a separate operator authentication client, a two-call bounded
  Operations Analysis Agent, and a deterministic offline Critic. Neither can
  create a return, refund, order change, or customer notification.
- Vue has a separate internal-operations panel whose token is stored separately
  from the customer token. It contains no raw chat, RAG chunks, trace, or PII.

Verified evidence:

- Python full regression: `163 passed`; Build 19 handoff, operations-agent,
  legacy-auth normalization, and order-access-boundary tests are included.
- Java Build 19 tests: `9 passed` (handoff service `3`, operations controller
  `3`, operations service `2`, MyBatis scan `1`). The Maven root's default
  `skipTests=true` was explicitly overridden for this result.
- Vue production build passed.
- Docker health checks passed for MySQL, migration, Redis, RabbitMQ, portal,
  admin, AI service and web. The `ai_case_handoff` migration exists.
- A real browser-proxy policy request returned a grounded customer answer with
  only `answer`, public fact/workflow fields and customer-safe diagnosis fields;
  no RAG, tool, intent or CaseHandoff field was present.
- A real customer-A policy-gap request created a minimum `policy_insufficient`
  CaseHandoff; the order administrator listed it and triggered one bounded
  operations analysis draft. The analysis returned aggregate data only and
  did not change orders, returns, or Outbox rows.
- Unauthenticated/customer operations access returned `401`; a product-admin
  token returned `403`; the order-admin test account returned the authorized
  analysis. A legacy Java `HTTP 200 + code 401` response is normalized to a
  customer-safe `401`.
- Four persistent local demo orders were created through the normal Java APIs:
  two for `build19_customer_a` and two for `build19_customer_b`. They are
  intentionally retained for later demonstrations; credentials are kept out
  of this document.
- During live negative testing, an order belonging to another member was
  correctly hidden. The first pre-fix run is retained as a local case record;
  the discovered bug was fixed so subsequent inaccessible-order probes return a
  safe order-number correction and create no new handoff.

## Final acceptance boundary

The local database counts before and after the operations analysis were
unchanged for orders (`69`), after-sales applications (`21`) and Outbox rows
(`0`); the two intentionally retained handoff records are the only new Build
19 coordination data. This proves the operations role is read-only for the
tested path, not that the stack has production availability, high-concurrency
throughput, complete crash recovery, or a real notification/workbench
integration.

Runtime fixes discovered during the live startup:

- Added the optional legacy MinIO configuration required by the pre-existing
  admin application to start in its Docker profile. No MinIO service or file
  upload capability was added to this Build.
- Added the explicit MyBatis scan for the new read-only operations DAO and a
  regression test for that scan.

Remaining boundaries and non-claims:

- The operations panel is available at the local Vue site, but no screenshot
  or production browser recording is claimed by this document; the tested
  browser-proxy API path and production bundle are the repeatable evidence.
- The local accounts, orders and handoff records are demo fixtures, not
  production data. No claim is made about production availability, model
  accuracy for all inputs, high-concurrency throughput, complete crash
  recovery, or downstream SMS/email/workbench delivery.
