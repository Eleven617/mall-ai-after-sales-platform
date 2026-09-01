# Build 20 Requirements Alignment: RAG 2.0 Hybrid Retrieval and Rerank

**Status:** approved and under construction on 2026-08-21. This document is
the scope gate for Build 20. It does not mark Hybrid Retrieval or reranking as
accepted until the committed evaluation suite, automated tests, and local
acceptance evidence have been recorded.

## Problem and customer-visible outcome

The current policy RAG path uses local BGE dense retrieval as its reviewed
baseline. Dense retrieval is useful for paraphrases such as “耳机试过还能退
吗”, but a dense-only ranking can miss a precise policy term; keyword-only
retrieval has the opposite weakness. A correctly retrieved policy can also be
ranked too low to be used safely by the existing evidence verifier.

Build 20 evaluates and implements this candidate pipeline:

```text
approved policy-query projection
  -> local Dense and local BM25 retrieval
  -> Reciprocal Rank Fusion (RRF)
  -> optional local Cross-Encoder rerank of allowed policy candidates
  -> existing semantic evidence verifier
  -> grounded answer or safe abstention
```

Customers keep the current public answer, fact-card, and after-sales workflow
experience. They do not see ranking mode, chunk IDs, BM25 scores, dense
distances, reranker scores, RAG text, prompts, evaluation reports, or model
diagnostics. The only customer-visible change permitted by this Build is a
more accurate policy answer or the existing safe “insufficient evidence”
response.

## Data boundary and retrieval safety

- Dense, BM25, RRF, and reranking receive a **minimal policy-query
  projection**, never a Bearer Token, order snapshot, logistics result,
  CaseHandoff, Trace, internal prompt, or full conversation history. The
  projection removes common order/phone/email/token-shaped identifiers and is
  bounded in length before local retrieval.
- The Cross-Encoder receives only that projection and the policy candidates
  selected by the service. It does not query Java, Redis, MySQL, Chroma
  metadata beyond the candidate text, or any customer/operations data.
- Retrieved policy text is untrusted data. It is delimited before it reaches
  an LLM; instructions inside a document or a query cannot replace the system
  policy, select tools, widen permissions, reveal internal data, or cause a
  business write.
- Existing Java authorization, return confirmation, idempotency, CaseHandoff,
  Outbox, customer/operations/developer role isolation, public DTO projection,
  and the semantic evidence verifier remain unchanged in responsibility.

## One real acceptance flow

```text
Customer asks a generic policy question at the existing Vue page
  -> FastAPI obtains only the policy-query projection
  -> selected retrieval mode returns allowed policy candidates
  -> evidence verifier selects supporting chunks or refuses
  -> existing answer generator returns a customer-safe answer
  -> browser/proxy response is checked to contain no RAG/internal fields
```

The separate developer/CI command runs the same versioned synthetic golden
suite against `dense`, `hybrid`, and `hybrid_rerank`. It records retrieval
metrics, latency and local/provider-cost boundaries; it is never appended to a
customer request.

## Build 20.0: reviewed golden suite and baseline

A versioned, project-owned synthetic suite is added before changing the
default customer path. It includes the prior reviewed policy cases plus new
human-reviewed cases for:

1. Chinese paraphrases and colloquial expressions;
2. exact policy terms such as seven-day return, activation, freight insurance,
   invoice and price protection;
3. near-but-wrong policy questions and old-versus-current-rule conflicts;
4. questions with no approved policy answer;
5. adversarial/unrelated candidate text and RAG indirect-prompt-injection
   fixtures.

Each case records allowed evidence sections, forbidden evidence where useful,
and whether the safe end state is an answer or abstention. The evaluator
reports Recall@K, MRR, nDCG@K, deterministic evidence/abstention contracts,
p95 latency, and provider/local cost metadata. A live grounding profile is
explicitly optional and separately labeled because it uses DeepSeek for the
pre-existing verifier and answer-generation stages.

## Build 20.1 and 20.2 implementation choices

- `dense` remains a selectable baseline and the initial runtime default.
- `hybrid` runs local dense and BM25 candidate retrieval, fuses ranks using
  RRF, and retains provenance internally for the evaluator. It is not a
  “BM25 fallback when embedding fails”; an embedding failure remains a safe
  retrieval-unavailable result for the customer path.
- `hybrid_rerank` reranks only the Hybrid Top-N allowed policy candidates with
  a local ONNX Cross-Encoder. A missing/corrupt reranker model fails safely to
  the already-selected Hybrid candidates for experimental runs and is recorded
  as unavailable; it does not manufacture an answer.
- A one-time local `BAAI/bge-reranker-base` ONNX model download is expected to
  be about 1.04 GB. It uses normal network access only during setup; customer
  demos do not need VPN after the model is packaged. The download is preceded
  by a disk-space check and its presence is verified before Docker acceptance.
- No LLM query rewrite is added in this Build. It may be evaluated later only
  if the golden set shows a concrete gap that Hybrid/Rerank does not address.

## Cost, latency, fallback, and decision rule

- Dense/BM25/RRF/Cross-Encoder ranking is local: no extra DeepSeek token cost
  is introduced by these stages. The reranker adds local CPU latency and model
  disk/image size.
- The existing evidence verifier and answer generator retain their existing
  bounded DeepSeek calls; Build 20 does not run an evaluation for each customer
  request.
- Offline metrics distinguish `environment_blocked` (embedding/reranker/model
  unavailable) from a measured quality failure. Provider timeouts are not
  scored as retrieval regressions.
- The default stays `dense` unless the same golden suite shows that another
  mode preserves or improves safety/abstention and gives a reproducible
  retrieval/ranking benefit within an acceptable local p95 latency budget.
  No small local corpus result is described as production accuracy.

## Explicit non-goals

- No Build 21 durable checkpointer/HITL state or Build 22 live-model/trace
  evaluation work.
- No LangChain, MCP, Elasticsearch, agent swarm, Java/DB schema change, new
  user role, customer-facing RAG debug panel, or policy authoring UI.
- No query rewrite model, automatic policy update, automatic Prompt/code
  change, customer-data ingestion, business write, or relaxation of the
  no-evidence gate.
- No claim of a production-size corpus, production throughput, general model
  accuracy, or online experiment result based solely on this local demo set.

## Anticipated file boundary

| Area | Planned files |
| --- | --- |
| Retrieval implementation | `app/services/policy_retrieval.py`, `bm25_retriever.py`, `cross_encoder_reranker.py`, existing `rag_service.py` / `vector_store.py` / schemas/configuration |
| Evaluation | versioned `evals/rag2_golden_cases.v1.json`, RAG 2.0 evaluator and explicit scripts/tests |
| Local model delivery | `requirements.txt`, `.env.example`, Dockerfile / `.dockerignore` / Compose only as needed to package the reviewed local reranker |
| Evidence safety | existing RAG and verifier prompt rendering plus injection-contract tests |
| Evidence records | Build 20 report, backlog/master-plan/execution-control updates only after all acceptance checks pass |

## Completion gate

1. The same versioned suite can run dense, Hybrid, and Hybrid+Rerank repeatedly.
2. Tests cover BM25/RRF determinism, candidate provenance, model isolation,
   reranker failure, no-evidence behavior, and indirect prompt injection.
3. All supported results map to allowed policy evidence; unsupported/injection
   cases keep the safe abstention boundary.
4. A comparative report has Recall@K, MRR, nDCG@K, deterministic
   grounded/abstention outcomes, p95 latency and cost metadata for every mode.
5. Python regression, Vue production build, Docker health and one real generic
   customer RAG browser/proxy smoke pass without leaking internal fields.
6. The final report identifies the selected default (or explicitly retains
   dense) and states the local-corpus measurement limits.

## Recovery snapshot

Before Build 20 edits, the affected source, tests, evaluations, Docker files
and planning documents were copied to:

`C:\\Users\\12969\\Desktop\\mall\\snapshots\\build20-rag2-prechange-20260821`

## Construction and acceptance result (2026-08-21)

Build 20.0--20.2 are complete. The project now has a versioned 52-case golden
suite, local BM25 + Dense parallel retrieval, deterministic RRF, local ONNX
Cross-Encoder reranking, an explicit retrieval/grounding evaluator and
prompt-injection contracts. The customer default remains Dense because the
same golden suite measured no ranking benefit from Hybrid/Rerank and a large
local reranking latency cost. Detailed evidence, the discovered activation and
tangential-source regressions, their generic verifier-contract fix and all
local limits are in `docs/BUILD_20_RAG2_EVALUATION.md`.
