# Project Execution Control

## Purpose

This document is the compact mainline handoff for the mall AI project. It does
not replace `AI_PROJECT_MASTER_PLAN.md`; it records the currently approved
scope, execution order, verified state, and branch-to-mainline handoff format.

Last updated: 2026-08-25.

## Product Target

Build a production-oriented, locally demonstrable ecommerce after-sales AI
platform. "Production-oriented" means the project must demonstrate real
authorization, data ownership, evidence grounding, reliable write boundaries,
asynchronous event design, retry/idempotency design, observability, and
repeatable deployment evidence.

It does not mean claiming that a student-local Docker stack is a production
release, or inventing a warehouse, payment, carrier, or notification system
that has no real business contract behind it.

The flagship path remains:

```text
Natural-language after-sales request
  -> evidence-grounded information collection
  -> Java-verified order and product ownership
  -> RAG policy evidence
  -> explicit customer confirmation
  -> Java after-sales write
  -> customer-visible status tracking
```

## Current Verified State

| Area | Current state | Evidence / limitation |
| --- | --- | --- |
| Java, JWT, order ownership | Built and locally verified | Two-account access/write boundaries are covered locally. |
| Redis conversation and after-sales state | Built and locally verified | Drafts, proposals, expiry, member scope and cross-request resume exist. |
| RAG | Build 20 RAG 2.0 built and locally measured | Dense, BM25+Dense+RRF and local Cross-Encoder paths are compared on 52 synthetic reviewed cases. `chunk-v2` now records explicit policy metadata and server-owned version/date/language/type prefiltering; Dense remains default because Hybrid/Rerank did not show a local ranking gain; no production accuracy claim. |
| After-sales write workflow | Built and locally Docker-verified | A real browser-proxy chain verified RAG proposal -> confirmation -> Java write -> customer status card; same-key replay returns one record, tampering is rejected, and cross-account status is hidden. Recovery code is unit-tested; no production availability claim. |
| Customer status tracking | Built and locally Docker-verified | Account A can read its record; account B cannot. |
| Agent orchestration | Custom ReAct baseline plus Build 14 LangGraph diagnosis graph built, unit-tested and locally Docker-verified | A disposable two-account run verified order/logistics/RAG evidence, cross-account fact isolation and no diagnosis write operation; no production model-quality claim. |
| Build 17 quality checkpoints | Built, unit-tested and locally exercised | Python `148/148`, offline Agent `6/6`, diagnosis `4/4`, semantic verifier `36/36`; grounding hard contracts `15/15` with one wording review signal. Metrics are explicit local evidence, not production claims. |
| Build 18 event delivery | Built and locally Docker-verified | Java Outbox, RabbitMQ publication and idempotent delivery are implemented; this is not production throughput or recovery evidence. |
| Build 19 controlled Multi-Agent | Built, unit-tested and locally live-verified | Customer diagnosis, operations analysis and AI quality-evaluation roles have separate contracts and data scopes. The quality Agent runs only versioned synthetic cases behind a dedicated developer role; Docker proxy verified 9/9 cases with no business writes. A visual screenshot/recording remains presentation evidence, not a production claim. |
| Build 21 durable HITL diagnosis | Built, unit-tested and Docker-live-verified | A separate allow-listed LangGraph checkpoint persists only the waiting reason/owner hash/TTL, never raw diagnosis state or credentials. Anonymous and authenticated A/B website-proxy pause→restart→resume/rejection paths passed; no business write is part of this flow. |
| Build 22 unified Agent reliability closure | Built, unit-tested and locally Docker-verified | Unified after-sales now contains the bounded read-only ReAct subflow; `trace-v2` is allow-listed and non-blocking. Contract-mock trajectory/red-team 17/17 and live-model synthetic 3/3 passed using only synthetic fixtures. Manual logged-in operator/developer browser replay was not repeated in this batch; no production claim. |
| Delivery | Docker Compose local stack is healthy | Remote deployment, operational monitoring and final demo evidence remain pending. |

Progress is intentionally reported with two denominators:

- Interview-ready local demonstration: about 82%.
- Production-grade operational platform: about 52%.

## Execution Rules

1. One named build batch at a time: define acceptance criteria, construct and
   verify it, then teach it.
2. Mainline owns code changes, architecture decisions, scope changes and the
   next-build decision.
3. A branch thread studies one completed build only. It must not independently
   change code, introduce a framework, or advance the plan.
4. Each branch returns one compact handoff using the template below. Mainline
   decides what becomes a durable project fact.
5. Do not repeat already learned JWT/Java/Redis basics in later builds unless a
   new behavior depends on them.
6. Every claim distinguishes: implemented, unit-tested, locally live-verified,
   and production-verified.

## Branch Handoff Template

```markdown
## Build XX Handoff

- Status: built / unit-tested / locally live-verified / not verified
- Problem solved:
- User-visible behavior:
- Request flow in at most 8 lines:
- Three key files and why they matter:
- Key technical decisions and rejected alternatives:
- Tests / metrics actually passed:
- Known limitations and non-claims:
- Interview concepts learned:
- Recommended next action:
```

## Approved Build Sequence

1. **Build 14A learning**: brief Java -> FastAPI -> Vue code walkthrough of
   already verified customer status tracking.
2. **Build 14 learning**: study the completed LangGraph diagnosis graph before
   changing it. It is built, unit-tested and locally live-verified; see
   `docs/BUILD_14_ORDER_DIAGNOSIS_AGENT.md`.
3. **Build 15 archived approach**: the former customer/reviewer dual-mode and
   second LLM narration layer was removed after a requirement mismatch review.
   Keep the customer DTO projection and fixed RAG evaluations; see
   `docs/BUILD_15_REQUIREMENT_ALIGNMENT_AND_ARCHIVED_APPROACH.md`.
4. **Build 16 write reliability**: built, unit-tested and locally Docker-verified;
   see `docs/BUILD_16_RETURN_SUBMISSION_RELIABILITY.md`.
5. **Build 16.5 local Embedding portability**: replace the customer-demo
   Gemini/VPN vectorization dependency with a project-packaged local Chinese
   model. Historical Gemini measurements were compared before its provider,
   configuration and old vector collection were removed; it is not a fallback.
   The reviewed local corpus was rebuilt and remeasured. The customer page and
   Java/RAG workflow boundary do not change. A VPN-off browser smoke remains
   conditional on Docker's DeepSeek network path being healthy.
6. **Build 17 quality checkpoints**: built after the requirements-alignment
   note. Explicit profiles now report progress, per-case timing, token usage,
   bounded provider calls, and separate `review_required`, `quality_failed`,
   and `environment_blocked` outcomes. They never run in customer requests;
   see `docs/BUILD_17_QUALITY_CHECKPOINTS.md`.
7. **Build 18 event-driven after-sales lifecycle**: built, unit-tested and
   locally Docker-verified. A Java transaction writes the return application,
   Build 16 submission record and Outbox row; RabbitMQ delivery uses event-ID
   idempotency, bounded retry/backoff and a dead-letter path. See
   `docs/BUILD_18_REQUIREMENTS_ALIGNMENT.md`.
8. **Build 19 controlled Multi-Agent collaboration**: built, unit-tested and
   locally live-verified with separately scoped customer diagnosis, operations
   analysis and AI quality-evaluation roles. A real policy-gap handoff was
   analyzed by an order administrator; the third role uses only 9 versioned
   synthetic cases under a dedicated developer identity. Customer/operator
   denial, public DTO projection and no-business-write checks passed. See
   `docs/BUILD_19_REQUIREMENTS_ALIGNMENT.md` and
   `docs/BUILD_19_QUALITY_EVALUATION_AGENT.md`.
9. **Build 20 measured RAG 2.0 upgrade**: complete. The project expanded a
   versioned golden suite, implemented Dense/BM25/RRF/Cross-Encoder candidates
   and retained Dense by measured decision; see
   `docs/BUILD_20_RAG2_EVALUATION.md`.
10. **Build 21 durable Human-in-the-Loop diagnosis**: constructed, unit-tested
    and Docker-live-verified. It adds a sanitized Redis-backed LangGraph
    interrupt/resume checkpoint only to the missing-identifier read-only
    diagnosis gate; anonymous and authenticated A/B restart/browser-proxy
    recovery/rejection passed. See
    `docs/BUILD_21_DURABLE_HITL_REQUIREMENTS_AND_IMPLEMENTATION.md`.
11. **Build 22 unified after-sales Agent reliability closure**: constructed,
    unit-tested and locally Docker-verified. It integrates the bounded
    read-only ReAct investigation into the unified graph, adds `trace-v2`,
    deterministic trajectory/red-team CI gate configuration and a manual
    live-model synthetic profile without production data or writes. See
    `docs/BUILD_22_UNIFIED_AGENT_RELIABILITY_REQUIREMENTS.md`.
12. **Delivery and career evidence**: deployment runbook, demo recording,
   architecture diagram, resume bullets, project Q&A and mock interviews.

## Approved Platform Direction

The project will optimize for three demonstrable engineering proofs rather than
for a long list of framework names:

1. An evidence-driven LangGraph diagnosis Agent connected to authenticated Java
   business services.
2. Role-gated quality checkpoints and privacy-safe observability showing real
   evaluation and execution evidence, not invented production metrics; this is
   not a second customer/reviewer website.
3. A reliable event-driven after-sales lifecycle with idempotent delivery.

The later role-based Agent platform is not a generic agent swarm. Java-derived
identity and role determine the available capability profile; an LLM cannot
choose a role, grant a tool, widen a data scope or authorize a write operation.
MCP, a general Skill loader and cross-session long-term memory remain deferred
until a real second consumer or stable second business capability makes them
necessary.

## RabbitMQ Boundary

RabbitMQ is for asynchronous events and background jobs, not the synchronous
customer chat request path. It must never carry passwords or browser Bearer
Tokens. Build 18 writes a safe domain event to a Java transactional outbox with
the business state change, publishes it only after commit, and keeps undelivered
events retryable. Consumers use event IDs for idempotency, retry with backoff,
route terminal failures to a dead-letter path, and store an auditable delivery
result before acknowledging the message.
