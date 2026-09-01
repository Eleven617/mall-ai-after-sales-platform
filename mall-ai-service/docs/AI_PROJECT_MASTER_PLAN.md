# AI Project Master Plan

This document is the single source of truth for the project scope, build order,
and learning order. Read it before changing the plan or starting a new module.
For the compact current-mainline handoff, branch-study rules, and verified
execution snapshot, also read `docs/PROJECT_EXECUTION_CONTROL.md`.

For approved future ideas and their relationship to deployment, RAG, and Agent
work, see `docs/AI_PROJECT_EVOLUTION_BACKLOG.md`. For the later interview-learning
and mock-interview sequence, see `docs/PROJECT_INTERVIEW_KNOWLEDGE_MAP.md`. These
documents are planning/learning references; they do not override this delivery
order until a named build batch is approved.

## Product Goal

Build an ecommerce intelligent customer-support and order-exception handling
assistant. The product has three user paths:

1. Authenticated order and logistics queries backed by real Java services.
2. After-sales policy questions grounded in RAG evidence and source references.
3. An after-sales exception workflow: collect information, read real order data,
   retrieve policy evidence, propose an action, require confirmation, then invoke
   the Java after-sales endpoint or hand off to a human.

The third path is the flagship interview scenario. The first two are supporting
customer-service capabilities, not unrelated demos.

## Fixed Technology Choices

- Frontend: existing Vue mall frontend.
- Business system: Spring Boot, MyBatis-Plus, MySQL, Spring Security, JWT.
- AI service: FastAPI, Pydantic v2, httpx.
- LLM: DeepSeek using the OpenAI-compatible native Function Calling API.
- Embeddings: local `BAAI/bge-small-zh-v1.5` ONNX model is the only customer-demo
  embedding path. Gemini was compared against the reviewed evaluation set, then
  removed from runtime code, configuration and the local vector store; it is not
  a fallback.
- RAG: ChromaDB with source metadata and evaluation. The customer-facing path
  fails closed when the embedding provider is unavailable: it does not send
  policy text to the answer model and returns a distinct retriable/handoff
  response. Any future candidate model must be indexed separately and pass the
  reviewed evaluation before it can replace the local model; it cannot silently
  answer customers as a fallback. Build 20 measured Hybrid/Rerank against the
  reviewed local corpus and retained Dense as the default; see
  `docs/BUILD_20_RAG2_EVALUATION.md`.
- Conversation state: Redis in deployed environments; in-memory store only for
  local development and deterministic unit tests.
- Agent: custom ReAct remains the small baseline; Build 14 uses LangGraph for
  the multi-tool diagnosis graph because it has explicit loops and terminal
  branches. Build 21 adds a separate, Redis-backed persistent checkpoint only
  for a sanitized missing-identifier diagnosis pause; it does not persist the
  rich diagnostic State or replace Java write boundaries.
- Quality checkpoints: Build 17 now provides fixed offline and explicit
  local-live profiles after a requirements-alignment note defined users, data
  visibility, acceptance flow, non-goals, and model-cost/latency boundaries.
- Delivery: Docker Compose, structured trace logs, tests, README, and demo.

## External Reference Decision (2026-07-31)

`HuaiNan54321/ecom-service-agent` is an educational Agent reference, not a
replacement architecture for this project. We will study its ReAct loop,
tool-manager allow-listing, Skill progressive disclosure, evaluation sandbox,
and process/result metrics. We will implement only the ideas needed by this
project in our own code and with our own acceptance cases.

We will not copy its source code, prompts, documentation, Skill files, or test
dataset. Its custom authorization terms allow personal learning and portfolio
use but prohibit public redistribution of the original project. More
importantly, copying would make the implementation difficult to explain and
would not prove our own business decisions.

The reference does not change the primary differentiator: our AI service must
be connected to the Java mall's JWT, order ownership, RAG evidence, and
controlled after-sales write workflow. Evaluation/observability and capability
profiles are the first reference ideas to absorb after real Java integration.
Multi-Agent, MCP and a Skill loader require a real business boundary; they are
not default architecture choices.

## Explicit Deferrals and Entry Gates

- No LangChain migration, generic Multi-Agent swarm, client-selected role,
  standalone MCP server, general Skill loader, long-term user memory,
  Elasticsearch vector migration, Kubernetes deployment or private model
  hosting merely for resume keywords.
- Build 18's Outbox + RabbitMQ event path is complete with local Docker
  evidence; it is not claimed as a production deployment. Build 19's
  controlled multi-Agent implementation is unit-tested and Docker/browser-
  proxy live-verified, including an authorized operations analysis and role
  denial checks; visual recording and production deployment remain separate
  delivery evidence.
- No unsupported claims about model accuracy, production deployment, or live
  integration before they are measured and demonstrated.
- No wholesale rewrite based on an external teaching repository.

## Delivery Order

1. Record the archived Build 15 requirement decision, then complete the
   already verified Build 14A and Build 14 learning handoffs before changing
   the next module.
2. Build write reliability (Build 16): Java-verifiable idempotency,
   timeout-result recovery and retry-safe status lookup. Complete.
3. Remove the customer-demo Gemini/VPN Embedding dependency (Build 16.5):
   package a local Chinese ONNX model, isolate its vector collection and
   remeasure retrieval/grounding before the VPN-off presentation. Complete.
4. Build the P1 Agent quality checkpoints and privacy-safe observability (Build
   17), separating offline, local-live and future production evidence without
   adding a customer-facing reviewer website. Complete; see
   `docs/BUILD_17_QUALITY_CHECKPOINTS.md`.
5. Build one transactional Outbox + RabbitMQ after-sales status event path
   (Build 18). Complete; see `docs/BUILD_18_REQUIREMENTS_ALIGNMENT.md`.
6. Build 19's controlled role-based Agent platform is complete and frozen for
   learning. Teach the completed module, then preserve its acceptance evidence
   before moving to measured RAG upgrades.
7. Build 20 RAG 2.0: use a versioned corpus/measurement suite to implement and
   compare Hybrid Retrieval and reranking. Complete; Dense remains the default
   because the local evidence did not justify an online change.
8. Build 21 durable Human-in-the-Loop diagnosis: implement and verify a
   privacy-safe LangGraph interrupt/resume checkpoint for missing diagnostic
   identifiers. Code/unit and anonymous Docker restart/browser-proxy recovery
   are complete; authenticated two-account recovery verification is still required.
9. Finish repeatable delivery, demo evidence, resume bullets and interview
   preparation without overstating local verification as production release.

## Collaboration Rules

1. Work on one named module at a time.
2. Before a build batch, record the goal, technologies, changed files, and
   acceptance criteria.
3. During a build batch, implement and test without interrupting it with lessons.
4. During a learning batch, freeze implementation and study only the completed
   module from its large concept down to small code paths.
5. The learner owns architecture decisions, authorization boundaries, RAG
   evaluation criteria, and Agent failure branches. AI may generate scaffolding,
   repetitive code, tests, and documentation.
6. Every completion report must distinguish code written, unit tests passed,
   live integration verified, and deployment verified.

## Current Build Status (updated 2026-08-14)

Delivery steps 2--5 are **built and unit-tested**. These modules are frozen
while learning them; new features wait for the next named build batch.

  ### Build 12: Reproducible Local Delivery and Browser Demo (in progress)

- Compose, container definitions, readiness checks, demo-data scripts and
  documentation are built as one batch;
- the local Docker runtime is verified: all seven services became healthy, the
  Vue/FastAPI/Java public checks passed, and two disposable accounts proved
  login, Token propagation and cross-account order denial;
- a real Docker-served policy request produced a grounded answer; RAG source
  metadata remained server-side. The reviewed live grounding runner passed `15/15` hard
  contracts on the project-owned demo corpus, including three no-evidence
  refusals. This is small local evidence, not a production-accuracy claim;
- final browser click-through remains pending: visibly demonstrate login,
  policy answer without internal RAG fields, return proposal + one confirmation,
  and foreign-order denial
  before marking Build 12 complete;
  - this build will not introduce unrelated Agent, RAG, RabbitMQ-AI, Elasticsearch
    or Kubernetes features.

1. **Conversation state and context compaction**
   - Redis-ready session state with a local in-memory fallback.
   - Recent messages, compacted summary, structured business facts, pending
     tool calls, return drafts, and return proposals are stored separately.
   - A compaction policy reduces old chat history without dropping critical
     facts such as an order number.
2. **RAG evidence and evaluation**
   - Retrieved chunks carry server-generated document and section metadata.
   - The service refuses or hands off when no retrieved evidence meets the
     configured distance threshold.
   - Retrieval evaluation cases and a Recall@K script are included.
3. **Order-exception workflow**
   - A server-side draft collects order number, product, and reason across
     requests, binds itself to the login authorization fingerprint, and
     expires.
   - Ambiguous numeric input asks for clarification; phone-only input is never
     promoted to an order number.
   - The workflow verifies the current user's Java order snapshot, obtains RAG
     policy evidence, produces a client-safe proposal, and needs a one-time
     explicit confirmation before its Java write call.
4. **Agent hardening and reviewed evaluation**
   - The custom Agent has only read-only tools, and stops on timeout, step,
     repeated-call, tool-failure, and unavailable-model branches.
   - Trace metadata is allow-listed and privacy-safe; workflow regression cases
     and the human-reviewed feedback loop are documented.
5. **Public response boundary and pending-task control (Build 05)**
   - The HTTP router serializes a customer-safe DTO instead of the internal
     orchestration result.
   - Raw tool results, intent metadata, RAG chunks, chunk IDs, and distances are
     kept server-side; the Vue page receives only public evidence and actions.
   - A customer can explicitly cancel a pending read-only query without
     executing a tool, and a later message can route normally.

Verification completed before Build 06: 49 Python unit tests pass; Python source
compilation, the Vue production build, and the Build 05 API-boundary/cancellation
tests pass.

### Build 06: Real login and identity-scoped conversation state

Build 06 code is complete and frozen for learning:

- FastAPI delegates `/auth/login` and `/auth/me` to Java `/sso/login` and
  `/sso/info`; it does not sign or interpret JWTs;
- authenticated conversation state uses a server-derived member scope plus the
  browser's public conversation ID;
- return drafts/proposals bind to the Java-verified member ID and support a
  refreshed Token for the same member;
- Vue has a real login/logout panel and never asks the customer to paste a raw
  development Token;
- `scripts/verify_auth_flow.py` defines the two-account live acceptance matrix.

Build 07 has now completed the local live-integration evidence: 68 Python unit
tests pass, Vue production build passes, and two disposable accounts verified
Java login, JWT forwarding, order ownership, Redis-scoped state, real AI
logistics, policy-backed proposal, explicit confirmation, duplicate rejection,
and cross-account write rejection. Details are recorded in
`docs/BUILD_07_LOCAL_LIVE_INTEGRATION.md`.

Not yet verified: browser click-through recording, remote-server deployment,
production observability, and vector-retrieval quality beyond the reviewed
calibration set.
Gemini's local proxy was unavailable during the Build 07 after-sales case, so
that case used the reviewed local lexical-evidence fallback; it is not evidence
for a vector-quality or hybrid-retrieval resume claim.

On 2026-08-04, a separate live Gemini vector-retrieval calibration over the
reviewed local policy set measured 7/7 threshold-filtered supported retrieval
hits and 4/4 correct no-evidence refusals at a Chroma cosine-distance threshold
of 0.48. The previous 0.75 threshold admitted all four unsupported questions as
evidence. This is useful local evidence, not a broad production-accuracy claim;
the report and limits are in `docs/RAG_EVALUATION_EVIDENCE_2026-08-04.md`.
After the calibration and fallback-safety regression, the full Python suite
passes 73 tests.

Before any live Gemini/vector RAG evaluation, explicitly ask the learner to
enable the required VPN/proxy. A provider-connection failure must be reported
as an environment issue, never recorded as a retrieval-quality result.

### Build 08: Offline Agent Evaluation Runner

Build 08 is complete and verified locally:

- `evals/agent_cases.json` provides six reviewed synthetic cases that replay
  the real read-only Agent control flow with scripted model/tool boundaries;
- the runner records process checks (tool sequence, step bound, trace events)
  and result checks (fact-source boundary, pending task, controlled fallback)
  without emitting raw messages, tool arguments, model prose, or credentials;
- the initial offline report is 6/6 cases passed, with 26 process checks and
  20 result checks passed; the full Python suite is 70 tests passed.

This is deliberately an offline regression baseline. It is not evidence of
online model tool-selection accuracy, live RAG vector quality, browser flow,
or production deployment.

### Build 09: RAG Reliability and Grounding Contracts

Build 09 is complete and locally verified:

- embedding-retrieval failure is distinct from no-evidence and fails closed;
  no policy text is sent to the answer LLM;
- answer-generation outage is also distinct from no-evidence;
- a return draft is preserved but no proposal/write path is created while
  trusted policy retrieval or answer generation is unavailable;
- `evals/rag_grounding_cases.json` defines six reviewed synthetic grounding
  contracts. The evaluator separates hard safety checks from fact-marker review
  signals, and separates environmental provider outages from quality failures;
- a live generic-policy run passed 6/6 hard contracts and 6/6 fact-marker
  review signals on 2026-08-04. This is a small local sample, not a production
  accuracy claim.

Details and limits are in `docs/BUILD_09_RAG_RELIABILITY_AND_GROUNDING.md`.

### Build 10: Policy Corpus and Evaluation Expansion (complete)

- The project-owned demo knowledge base now has 15 policy sections, clearly
  labelled as demo business rules rather than real merchant terms;
- retrieval evaluation expanded from 11 to 36 reviewed synthetic cases, and
  grounding contracts expanded from 6 to 15;
- a deterministic corpus-contract validator detects missing policy references,
  duplicate IDs and invalid no-evidence expectations before re-indexing;
- focused offline tests pass;
- live Gemini re-index and retrieval measurement completed. Vector Top-3
  retained 28/28 supported cases at distance `0.48`, but rejected 0/8 reviewed
  no-evidence cases, demonstrating that threshold tuning alone was insufficient.

Details are in `docs/BUILD_10_POLICY_CORPUS_AND_EVALUATION_EXPANSION.md`.

### Build 11: Semantic Evidence Verification (complete)

- vector retrieval remains the candidate stage; a DeepSeek JSON verifier now
  decides whether candidate policy text explicitly supports the exact question;
- server code validates every selected chunk ID and sends only accepted chunks
  to answer generation; verifier failure blocks answer generation and
  after-sales proposal/write progression;
- a batch embedding path protects the active local index from provider failure
  during re-indexing and reduces evaluation-provider call count;
- live reviewed evaluation on 2026-08-04: vector-plus-verifier retained 28/28
  supported cases and rejected 8/8 no-evidence cases; full grounding passed
  15/15 hard contracts, while the latest rerun retained two wording-only
  manual-review signals.

This is local evidence for a small, reviewed demo set, not a production or
general-accuracy claim. Hybrid retrieval and reranking remain deferred until a
larger evaluation demonstrates a measurable ranking gap. Details are in
`docs/BUILD_11_SEMANTIC_EVIDENCE_VERIFICATION.md`.

## Build 14 Status

Build 14 construction is complete and frozen for learning. The LangGraph
diagnosis graph, safe public response, four-case offline evaluation and Vue
production build are verified. A Docker-local, two-account live run also
verified a real order/logistics/RAG diagnosis, cross-account fact isolation and
zero diagnosis write operations. The reusable verifier is
`scripts/verify_build14_live.py`; see
`docs/BUILD_14_ORDER_DIAGNOSIS_AGENT.md`. This is not a production or
general-model-accuracy claim.

## Build 17 Status

Build 17 construction is complete. It adds an explicit, bounded developer/CI
runner for the committed offline Agent/diagnosis cases, local retrieval
measurements, live semantic verification, and live grounding contracts. The
runner reports progress, per-case elapsed time, safe token/latency aggregates,
and separate `review_required`, `quality_failed`, `environment_blocked`, and
`budget_exhausted` outcomes. It has no customer route, reviewer UI, or
per-request model call. The latest local evidence is documented in
`docs/BUILD_17_QUALITY_CHECKPOINTS.md`; it is not a production model-quality
or cost claim.

## Build 18 and Build 19 Status

Build 18's transactional Outbox + RabbitMQ status-event path is complete and
locally Docker-verified; it is not a production throughput or crash-recovery
claim. Build 19 is also complete and frozen for learning: the customer
diagnosis, authorized operations-analysis and AI quality-evaluation roles have
separate data scopes and output contracts. The quality role only replays
versioned synthetic cases behind a dedicated developer identity. A real
policy-gap handoff was analyzed by the order-admin role, while customer and
non-developer admin access were rejected. Full evidence and known local-demo
limits are recorded in `docs/BUILD_19_REQUIREMENTS_ALIGNMENT.md` and
`docs/BUILD_19_QUALITY_EVALUATION_AGENT.md`.

## Build 20 Status

Build 20 RAG 2.0 is complete and locally measured. It added a 52-case synthetic
golden suite, local Chinese BM25 + Dense RRF, a local ONNX Cross-Encoder
experiment, safe policy-query projection and prompt-injection contracts. The
same suite retained Dense as the default: Hybrid did not improve MRR/nDCG and
Hybrid+Rerank added major local CPU latency. This is a measured local
engineering decision, not a claim of production RAG accuracy. See
`docs/BUILD_20_RAG2_EVALUATION.md`.

## Delivery Evidence Work (Runs Alongside Named Builds)

Repeatable delivery evidence remains open, but it does not override the
approved Build 15--20 sequence. Each named build must add or refresh the
evidence relevant to its own scope:

1. Keep a repeatable local startup/runbook and Vue browser click-through for
   the verified two-account and after-sales scenarios.
2. Keep offline evaluation reports separate from manually verified live-case
   reports; never treat scripted results as general online-model evidence.
3. Capture a short evidence-backed demonstration after each user-visible build,
   then assemble the final end-to-end recording, resume bullets and interview
   explanations.
4. No build is marked complete until its documented acceptance evidence exists;
   this is a verification gate, not a blanket ban on the next approved build.

## Fixed Learning Protocol

For every module, follow this exact order and do not change the project plan
mid-lesson:

1. Start with the **large problem**: why this module exists in the product and
   what user risk it prevents.
2. Split it into a small, fixed set of **sub-problems**.
3. Learn one sub-problem through its request flow, key code, and one test or
   experiment.
4. Check understanding with a short explanation in the learner's own words.
5. Only then move to the next sub-problem; code changes wait for the next
   named build batch.

Completed builds are frozen while they are being learned. The immediate
learning and build order is now:

1. Finish the Build 14A customer-status walkthrough, then study the completed
   Build 14 LangGraph diagnosis graph using the fixed
   large-problem -> request-chain -> key-code -> test order.
2. Study the completed Build 16 write-reliability implementation before adding
   another write workflow.
3. Study the completed Build 17 quality checkpoint implementation using its
   requirements note, one execution flow, key files, and live/offline evidence.
4. Study the completed Build 18 Outbox + RabbitMQ status-event path, then
   decide whether the available data supports a genuinely separate operations
   role.
5. Study the completed Build 19 controlled Multi-Agent collaboration and its
   role/data/contract boundaries before changing the next module.
6. Expand retrieval only after its evaluation corpus shows a measurable gap;
   collect delivery evidence alongside every completed build.

## Controlled Iteration Policy

The project supports a small, safe version of "self-audit" in delivery step 5:
record allow-listed, privacy-safe traces; identify failed or ambiguous cases;
let an AI assistant propose candidate test cases or fixes; require a human to
review them; then run the full regression suite before accepting a change. The
model must not autonomously change live business rules, write production code,
alter authorization logic, or update policy data. See
`docs/WORKFLOW_EVALUATION_AND_FEEDBACK.md` for the operational loop.

RAG documents may be refreshed through a reviewed knowledge-base update and
re-indexing process. Business workflow rules, authorization, confirmations,
and Java write contracts remain versioned backend/configuration changes with
tests and human approval.
