# Build 03 — Order-Exception Workflow and Agent Guardrails

## Goal

Complete the flagship after-sales workflow without allowing an LLM to authorize
or directly write business data:

```
natural-language return request
→ collect missing order / product / reason across requests
→ verify the current user's order through Java
→ retrieve after-sales policy evidence
→ present a proposal
→ explicit confirmation
→ Java creates the return application
```

## Technology Boundary

- FastAPI owns draft state, field collection, policy lookup orchestration, and
  safe response shaping.
- DeepSeek may extract a product hint/reason but never supplies trusted order
  item IDs, prices, member identities, or authorization decisions.
- Java validates JWT, order ownership, item ownership, order status, and
  duplicate after-sales applications before the write.
- RAG supplies policy evidence. If no evidence passes the configured threshold,
  the workflow hands off instead of creating a proposal.
- The existing ReAct Agent remains read-only: it receives no return-write tool.

## Acceptance Criteria

1. A return draft persists order, product, and reason collection across
   requests, is bound to the same authorization fingerprint, and expires.
2. A message with one explicit order number plus ordinary extra text can
   continue safely; multiple plausible numbers or phone-only input causes
   clarification rather than guessing.
3. A multiple-item order exposes only product labels to the client and asks for
   clarification until exactly one real item matches.
4. A policy answer with evidence is included before a proposal; no evidence
   produces a handoff and no pending write.
5. Confirmation is single-use and Java receives only order number, order-item
   ID, normalized reason, and description.
6. Structured, privacy-safe trace events record workflow/Agent decisions; the
   trace contains no raw bearer token, full user message, receiver information,
   or price.
7. Unit tests cover the workflow's happy path, ambiguous input, multiple-item
   clarification, no-evidence handoff, confirmation, and Agent error/guardrail
   behavior.

## Not Part of This Build

- Vue UI, Docker Compose, actual Redis process, real Java/DB/LLM deployment,
  production observability backend, LangGraph, hybrid retrieval, or Rerank.

## Built Artifacts

- `PendingReturnDraft` and `PendingReturnProposal` are stored separately from
  chat text and are bound to a hashed authorization fingerprint.
- Conservative identifier extraction rejects phone-only input and asks for
  clarification when there are multiple plausible order numbers or SKUs.
- The unified `/customer-service` entry point carries a draft through product
  selection, policy evidence, proposal, and a single-use confirmation.
- `mall_client` calls only the Java AI-specific read/write contracts. The
  browser never supplies an internal order-item ID, price, member ID, or order
  ownership decision.
- The custom ReAct Agent has a read-only allow-list, time/step/repetition
  limits, and privacy-safe structured trace events.
- `evals/order_exception_cases.json` records offline regression and future
  live-acceptance cases. `docs/WORKFLOW_EVALUATION_AND_FEEDBACK.md` describes
  the human-reviewed feedback loop.

## Verification Boundary

- Verified by deterministic Python unit tests: draft collection, ambiguous
  identifiers, multi-product selection, policy-evidence handoff, confirmation
  single-use, authorization binding, Agent tool blocking/repetition stopping,
  and trace redaction.
- Not yet verified: a running Java + MySQL service, real Redis persistence,
  real model/embedding/Chroma quality, browser integration, or deployment.
  These remain delivery work and must not be presented as completed production
  integration.
