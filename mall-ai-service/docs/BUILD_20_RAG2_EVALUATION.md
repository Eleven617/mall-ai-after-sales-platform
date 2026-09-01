# Build 20: RAG 2.0 Measured Hybrid Retrieval and Rerank

**Status:** built, unit-tested, locally measured, Docker-verified and
browser-proxy smoke-verified on 2026-08-21.

Build 20 implements Dense, Hybrid, and Hybrid+Cross-Encoder-Rerank paths, but
keeps **Dense** as the customer default. The current small, reviewed demo
corpus showed no ranking gain from Hybrid/Rerank, and the local Cross-Encoder
added significant CPU latency. The experimental paths remain selectable as
reproducible learning evidence rather than being presented as an online win.

**2026-08-28 hardening addendum:** policy chunks now use the `chunk-v2`
contract and a server-owned Metadata pre-filter for active version, effective
date, language and document type. The same 52-case Dense measurement kept its
Recall/MRR/nDCG exactly unchanged; see
`docs/RAG_CHUNKING_AND_METADATA_FILTERING_EVIDENCE.md`. This is not a switch
to Hybrid/Rerank or a production-quality claim.

## Customer boundary and implemented chain

```text
minimal policy-query projection
  -> Dense OR local Dense + BM25 in parallel
  -> RRF candidate fusion
  -> optional local Cross-Encoder Top-N rerank
  -> existing semantic evidence verifier
  -> grounded answer or safe abstention
```

Customers still see only the existing public DTO. A browser same-origin proxy
smoke returned only `answer`, `verified_facts`, `return_draft`,
`return_proposal`, `submitted_return_application`, `pending_action` and
`diagnosis`. It did not expose RAG text/source IDs, tool results, intent,
BM25/RRF/reranker scores, retrieval mode, Token or prompts.

The Reranker receives only a bounded policy-query projection and approved
policy candidates. It never receives a JWT, order/logistics data, full chat,
CaseHandoff, Trace, Java payload or internal prompt. Dense/BM25/RRF/Rerank are
local; existing Java authorization, confirmation/idempotency, public DTO
projection, three-role isolation, Outbox and no-evidence gates are unchanged.

## Golden suite and retrieval measurement

`evals/rag2_golden_cases.v1.json` contains 52 synthetic, manually reviewed
policy questions and two malicious/unrelated retrieval-text fixtures. It covers
colloquial rewrites, precise terms, near misses, old/current rule conflicts,
no-answer cases and RAG indirect-prompt-injection contracts.

One warm local Top-3 comparison measured:

| Mode | Recall@3 | MRR | nDCG@3 | Retrieval p95 | Decision |
| --- | ---: | ---: | ---: | ---: | --- |
| Dense | 1.000000 | 0.948718 | 0.962147 | 11.51 ms | Default retained |
| Dense + BM25 + RRF | 1.000000 | 0.935897 | 0.952683 | 12.12 ms | Experimental only |
| Hybrid + BGE Cross-Encoder | 1.000000 | 0.935897 | 0.952683 | 1943.75 ms | Experimental only |

The comparison made zero external model calls and incurred zero external token
cost. It does not convert local CPU/disk cost to a fictional currency number.
The candidate-stage `abstention_no_candidate_rate` is a diagnostic only; the
existing semantic verifier, not raw retrieval, makes the final abstention
decision.

## Grounding, failure discovery and correction

An explicit DeepSeek checkpoint (never part of customer requests) ran eight
reviewed Dense cases spanning policy evidence, no answer, activation,
misdelivery, old/current rules, compensation boundary and injection.

- Initial run: `6/8`. It exposed two genuine issues: activation was
  over-inferred from generic “used” wording, and a delay answer cited a
  tangential damage/loss source.
- Fix: the generic evidence-verifier contract now requires explicit key-state
  coverage and a minimum direct source set. This is a semantic evidence rule,
  not a growing keyword `if/else` list.
- Rerun: `8/8`, no environment-blocked cases; full-response p95 `2348.85 ms`;
  `12` provider calls and `7988` reported tokens. No price was supplied, so
  cost remains `null` rather than invented.
- A representative `hybrid_rerank` grounding smoke passed `2/2`, including
  prompt-injection abstention, but had `6412.55 ms` p95 full-response latency.

## Injection and local model delivery

Policy/query text is escaped and delimited as untrusted data before it reaches
the answer or verifier model. Their system prompts explicitly reject commands
embedded in policy text. Tests cover delimiter-closing, prompt disclosure and
output-contract attempts.

The local ONNX model is `BAAI/bge-reranker-base` (~1.08 GB). It is excluded
from Git, cannot auto-download during customer traffic, and can be installed
or checked explicitly with:

```text
python scripts/download_reranker_model.py --check-only
python scripts/download_reranker_model.py
```

Normal model setup needs network only once; customer demos do not need VPN for
embedding or reranking. Docker rebuilt only `mall-ai-service`; all eight
Compose services were healthy, and an in-container `hybrid_rerank` call loaded
the model with `reranker_unavailable=False`.

## Verification and limits

- Python full regression: `207 passed` (one pre-existing deprecation warning).
- Build 19 quality Agent regression: `9/9`.
- Vue production build: passed.
- Docker health: mysql, redis, mongo, rabbitmq, portal, admin, AI service and
  web all healthy.
- The corpus has 15 demo policy sections and the suite has 52 synthetic cases.
  This is local engineering evidence, not production RAG accuracy.
- A full 52-case live LLM grounding comparison was deliberately not run for all
  three modes; the full 52-case comparison is offline retrieval, while the
  live checkpoint is a bounded safety sample.
- Prompt-injection contracts prove this service boundary, not universal
  immunity for every future model or malicious corpus.
