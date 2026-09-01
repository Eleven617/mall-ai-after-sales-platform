# Build 18 Requirements Alignment: Reliable After-sales Events + Chat Scope

**Status:** built, unit-tested and locally Docker-verified on 2026-08-14.
This is local demonstration evidence, not a production-release claim.

This document records the agreed boundary before Build 18 code changes. It
combines one reliability path with one small customer-facing correction:

1. A transactional Outbox + RabbitMQ path for the `after_sales_application_created`
   status event.
2. SCS-1: constrain ordinary chat to the mall customer-service domain without
   turning it into a large keyword/`if`/`else` classifier.

## Problem and user-visible outcome

### Reliable after-sales event

Today Build 16 makes the return-application write idempotent, but it has no
durable business-event handoff after the Java transaction commits. Build 18
must guarantee that a successfully committed AI after-sales application has a
durable, retryable `after_sales_application_created` event even when RabbitMQ
is temporarily unavailable.

The customer continues to see only the existing safe after-sales application
card/list: application number, product, order number, status, time and a
handling note. The initial status is `pending_review` / `等待审核`.

The new event is an internal delivery mechanism. Customers never see an
outbox-row ID, RabbitMQ routing key, event ID, retry count, dead-letter message,
idempotency key, member ID or raw JSON event body.

### SCS-1 mall-chat boundary

The observed fresh-session `general_chat` path supplies `system_prompt=None`
to a second free-form DeepSeek call. It can answer as a generic DeepSeek
assistant about programming or quantum physics, which is outside the product
scope.

The corrected behavior is:

```text
hello / greeting             -> mall-service greeting and supported-capability hint
what can you help with?      -> concise mall order/logistics/after-sales capability hint
write Python / explain quantum -> polite out-of-scope mall-service boundary
order, logistics, policy, return, diagnosis -> existing routes unchanged
```

The model makes the semantic scope decision through a strict internal
`chat_scope` enum. The service maps that enum to reviewed templates. No raw
`chat_scope`, intent, prompt, model text or internal routing result enters the
public customer DTO.

## One real acceptance path

```text
Customer A logs in through Vue
  -> completes the existing evidence-grounded return proposal and confirms it
  -> FastAPI forwards the existing member-scoped confirmation to Java
  -> one Java transaction writes return apply + Build 16 submission record + outbox row
  -> publisher delivers the committed event to RabbitMQ
  -> idempotent consumer records the internal event delivery result
  -> customer refreshes the existing after-sales list and sees the Java-derived status
```

The browser accepts only the existing public DTO. It does not obtain event
delivery detail. Customer B must not see Customer A's application or any event
state.

## Data and authorization boundary

- Java derives the member from its existing JWT/Security context. The browser
  never sends a member ID, event ID, delivery state or idempotency key.
- The Outbox event contains the minimum internal identifiers required for
  delivery (`event_id`, application ID, member ID, event type, occurrence
  time). It carries no password, Bearer token, phone number, address, payment
  data, full order snapshot or LLM prompt.
- The consumer records delivery by unique event ID. Repeated RabbitMQ delivery
  must not create a second customer-visible state or notification.
- Java remains the business fact source; RabbitMQ does not authorize reads and
  does not decide a return application's status.
- The existing FastAPI `CustomerServicePublicResponse` remains the only
  customer-chat response projection. It must not gain `chat_scope`, RAG
  sources/context, tool result, intent, raw event data or evaluation fields.

## Model cost and latency boundary

- Outbox, publisher and RabbitMQ consumer add **zero** model calls.
- Existing RAG, tools, LangGraph diagnosis and return-confirmation flows retain
  their current calls and behavior.
- SCS-1 removes the current second free-form `general_chat` generation call.
  The existing structured intent call provides the allowed `chat_scope`, then
  the service uses a local template. This reduces one cloud round trip for
  ordinary chat rather than adding one.
- No claim about exact latency is made before measurement. The regression and
  live browser smoke will compare ordinary-chat behavior and ensure no new
  cloud call is introduced on that route.

## Failure and recovery rules

### Outbox and RabbitMQ

- If the Java transaction rolls back, neither the return apply nor its Outbox
  event exists.
- If the transaction commits but RabbitMQ is unavailable, the pending Outbox
  row remains in MySQL for bounded retry; the event is not lost.
- Publisher retries are bounded and observable. Terminal publish failures are
  retained as failed Outbox state for safe operator recovery; they are not
  silently discarded.
- RabbitMQ is at-least-once delivery. The consumer uses event-ID idempotency,
  retry/backoff and a bounded dead-letter path. It acknowledges only after
  recording the delivery result.
- The existing Docker log caps and the existing cancellation-failure queue stay
  in place. Build 18 must not introduce an infinite requeue/log loop.

### SCS-1

- If the intent model is unavailable or returns an invalid scope, the current
  controlled service-unavailable response is returned; no generic assistant
  answer is fabricated.
- If the model classifies a message as ordinary chat, only a reviewed
  mall-domain template is returned. It cannot claim generic DeepSeek identity
  or promise unrelated capabilities.

## Explicit non-goals

- No customer/reviewer/debug website, reviewer role, per-request evaluation or
  audit/trace UI.
- No automatic prompt, threshold or policy mutation from evaluation results.
- No new Gemini dependency, cloud embedding fallback, local generative-model
  hosting, MCP server, Skill loader or generic multi-agent swarm.
- No carrier, warehouse, refund, payment, SMS, email or staff-workbench
  integration. The event represents one real after-sales lifecycle transition,
  not a fictional full supply-chain system.
- No change to Build 16 idempotency semantics, RAG evidence gating, Java order
  ownership, LangGraph diagnosis permissions or public-RAG-field hiding.

## Verification required before Build 18 is declared complete

1. Java unit tests for transaction-side Outbox creation, duplicate submission
   replay without duplicate event, publisher retry state, consumer duplicate
   delivery and dead-letter behavior.
2. Python tests proving SCS-1 uses the intent/scope result and does not call
   the former free-form chat generator; existing RAG/tool/return routes remain
   unchanged; public DTO still excludes internals.
3. Full Python suite, targeted Java tests and Vue production build.
4. Docker live check: seven services healthy; a real Customer A return
   confirmation creates one application and one event delivery record; a
   same-key replay does not create a second application/event; Customer B
   cannot retrieve Customer A's record.
5. Browser/proxy smoke: a policy query and a logistics query still work;
   `帮我写 Python` and `量子力学是什么` receive the mall-scope response;
   public JSON has no RAG/internal/event/scope fields.

## Actual construction and verification

- SCS-1 uses the existing structured intent call to choose the internal
  `greeting` / `capability` / `out_of_scope` scope, then returns a reviewed
  local mall-service template. It does not make a second unrestricted model
  call. The prompt explicitly says that concrete knowledge, programming and
  writing requests are not greetings; `help me write Python` and the quantum
  physics smoke query both passed as out-of-scope replies.
- The Outbox retry clock is owned by MySQL: initial events are immediately
  eligible, while lease and retry timestamps are calculated with `now()` in
  the DAO. This fixed a real local Java/MySQL timezone mismatch that otherwise
  delayed a newly committed event by eight hours.
- The consumer directly listens for raw AMQP `Message` values. This fixed a
  real conversion failure caused by payload-type dispatch before the consumer
  could record its idempotent delivery row.
- Python full suite: 153/153 passed. Java Build 18 targeted tests: 13/13
  passed. Vue type check and production build passed.
- Docker acceptance: all seven services became healthy. A disposable local
  customer completed the existing proposal-and-confirmation flow; its event
  reached `PUBLISHED` with one `DELIVERED` consumer record. A second customer
  could not read that return application. Customer/public responses exposed no
  idempotency key, event ID, `chat_scope`, intent, RAG context/sources or tool
  result.
- The normal policy smoke returned the reviewed quality-return freight answer;
  the logistics smoke asked for the missing order number without executing a
  query.

## Known local limits

- One intentionally pre-fix local event remains in the after-sales dead-letter
  queue as failure-path evidence. It is not customer-visible and was not
  deleted during verification.
- Existing Java request logging was observed to include sensitive login fields.
  That pre-existing global logging issue is not fixed by Build 18 and is
  recorded as a separate security follow-up.
- This build does not prove broker outage recovery across a process crash,
  production monitoring/alerting, or production-scale throughput.

## Pre-change recovery snapshot

Before any code changes, the existing touched files were copied to:

`C:\Users\12969\Desktop\mall\tmp\build18-scs1-prechange-20260814`

The snapshot is recoverable reference material only; it does not replace
normal targeted tests or change the active code.
