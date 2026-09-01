# Build 05 — Public Response Boundary and Pending-Task Control

## Goal

Make the browser API intentionally customer-safe, and let a customer explicitly
cancel a pending read-only query before starting another question.

## Problem being solved

The existing service result mixes public UI fields with learning/debug fields
such as `intent`, `tool_result`, `rag_context`, source chunk identifiers, and
vector distances. The Vue client does not need those internal values.

The existing pending order/logistics/SKU flow can continue after a missing
identifier, but it has no explicit cancellation action. A customer can become
stuck in a clarification loop when they change their mind.

## Technology and boundaries

- FastAPI exposes a dedicated public response DTO from the HTTP router.
- Internal service results remain available to Python tests and server-side
  orchestration, but are not serialized to the customer browser.
- Raw RAG chunks, internal tool results, route/intent metadata, trace data,
  source chunk IDs, and vector distances remain internal.
- Vue renders only public evidence labels and a server-defined pending-task
  cancellation action.
- Cancellation clears only a pending read-only query. It never creates or
  changes an order, return application, or authorization state.

## Planned changes

1. Add public response/source/action schemas and a server-side mapper.
2. Change `/customer-service` to serialize only the public DTO.
3. Add an explicit `取消查询` path for pending order/logistics/SKU tools.
4. Render a public pending-task card and cancellation control in Vue.
5. Add API boundary and cancellation regression tests.

## Acceptance criteria

1. The HTTP response never contains `intent`, `tool_result`, `rag_context`,
   `chunk_id`, or vector `distance`.
2. The customer receives the policy answer; source metadata remains internal for
   server-side tests and evidence checks.
3. A pending query response declares a safe `pending_action` with a fixed
   cancellation message.
4. Sending `取消查询` clears the pending query and never executes a tool.
5. A later message can be routed normally after cancellation.
6. Existing return-draft and return-proposal confirmation/cancellation behavior
   remains unchanged.
7. Python tests and the Vue production build pass.

## Explicit non-goals

- Real Java login, account roles, Redis runtime, and Docker deployment.
- A production observability dashboard or a browser-visible raw debug panel.
- Natural-language task switching without an explicit cancellation action.

## Implemented

1. `/customer-service` now projects the internal orchestration result onto a
   dedicated customer-safe response DTO before serializing it to the browser.
2. Retrieval metadata, including document names, section paths, chunk IDs and
   vector distances, stays on the server; the browser receives only the answer.
3. Missing order-number or SKU queries expose a constrained pending action;
   the only browser action is the fixed `取消查询` message.
4. An explicit cancellation clears a pending read-only query without executing
   a tool, then permits the next customer message to be routed normally.
5. The Vue client renders the answer and the cancellation action, but does not
   render internal route, intent, tool-result, RAG-context, trace, or retrieval
   fields.

## Verification

- Python syntax compilation: passed.
- Python regression suite: 49 tests passed, including public-response boundary
  serialization and pending-logistics cancellation coverage.
- Vue production build: passed.

## Honest integration status

This build is verified with local Python mocks and API-contract tests. It has
not yet been verified against a real Java login, two separate user accounts,
the Java mall APIs, Redis runtime, a live model provider, Docker, or a deployed
environment. Those are separate future milestones, not completed claims.
