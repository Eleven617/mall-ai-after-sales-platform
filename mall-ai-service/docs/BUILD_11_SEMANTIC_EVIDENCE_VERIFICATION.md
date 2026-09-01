# Build 11: Semantic Evidence Verification

## Problem

After Build 10, vector Top-3 recall was strong on the reviewed corpus but a
single cosine-distance gate could not simultaneously retain all supported
policies and reject all absent-policy questions. A query about cross-border
returns, for example, is semantically close to a normal return-method policy
without being answered by that policy.

## Decision

Keep vector retrieval as the candidate-recall stage. Add a second, narrow LLM
stage that decides whether the retrieved policy text explicitly supports a
safe policy response to the exact question.

This is not an autonomous Agent and it does not decide business facts. Its only
output is strict JSON:

```json
{"sufficient": true, "supporting_chunk_ids": ["server-known-id"]}
```

The server checks that every returned ID belongs to the retrieved candidates.
It sends only those accepted chunks to the final answer model. A false verdict
returns `no_evidence`; malformed JSON, an invented ID, or an unavailable
verifier returns a separate fail-closed state.

## Request Path

```text
question
  -> Gemini vector retrieval (Top-K candidates)
  -> distance gate
  -> DeepSeek evidence verifier (strict JSON)
  -> server validates selected chunk IDs
  -> DeepSeek policy answer using selected chunks only
```

For an order-exception proposal, verifier unavailability preserves the verified
return draft but blocks proposal creation and the Java write path.

## Reliability Changes

- Corpus ingestion obtains all embeddings before deleting the active Chroma
  collection, so an external-provider failure does not erase the last good
  local index.
- Gemini's batch embedding endpoint is used for both indexing and one-query
  retrieval; the evaluation runner batches its 36 query embeddings.
- RAG distinguishes `no_evidence`, `retrieval_unavailable`,
  `evidence_verification_unavailable`, and
  `answer_generation_unavailable`.
- Grounding checks now understand clear negated claims such as "不会自动赠送
  积分" without hiding an affirmative claim in a later sentence.

## Live Evaluation, 2026-08-04

All questions were reviewed, synthetic and non-personal.

| Evaluation | Result | Meaning |
| --- | --- | --- |
| Vector only, 36 cases, distance `0.48` | supported `28/28`, no-evidence `0/8` | Candidate retrieval has an abstention gap. |
| Vector + semantic verifier, 36 cases | supported `28/28`, no-evidence `8/8` | The verifier resolved this reviewed local gap. |
| Full answer grounding, 15 cases | hard contracts `15/15`; latest fact-marker review `13/15` | Responses used expected source paths and made no forbidden hard claims; two wording variants remain marked for human review. |

This is not a claim of general RAG accuracy or production readiness. The data
set is small, the policy source is a demo corpus, and model latency/cost need
measurement before deployment. The latest live grounding rerun retained all
hard contracts but produced two wording variants that did not match the
reviewed fact markers, illustrating why paraphrase-sensitive signals remain
manual-review inputs rather than an accuracy claim. New policies, prompts,
models, or retrieval settings require the same regression run.

## Retrieval Architecture Decision

Hybrid retrieval and reranking are not added in this build. The measured issue
was semantic evidence sufficiency, which the verifier addressed on the current
set. Reconsider Hybrid/Rerank only after an expanded reviewed set reveals a
remaining retrieval-ranking gap, and compare recall, abstention safety,
grounding, latency and cost in an A/B report.
