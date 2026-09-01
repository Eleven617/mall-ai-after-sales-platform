# RAG Future Upgrade Decisions

Status: Build 11 completed fail-closed semantic evidence verification on the
current reviewed local corpus. Secondary retrieval, hybrid retrieval, and
reranking remain future work unless new measurement proves their value.

## 1. Accuracy Takes Priority During Provider Failure

### Build 09 implementation

The former local lexical fallback was removed from the customer-answer path.
When local embedding retrieval raises an exception, the service returns a
distinct `retrieval_unavailable` result with no sources and does not call the
answer LLM. The return workflow preserves its draft and blocks proposal/write
creation until trusted policy retrieval is available again.

### Approved V1 delivery behavior

The V1 customer path returns a distinct `retrieval_unavailable` customer-safe
response. It does not call the answer LLM or claim that the policy does not
exist. The response asks the customer to retry or contact human support.

This distinguishes two different states:

- `no_evidence`: vector retrieval completed, but no policy evidence passed the
  evidence gate.
- `retrieval_unavailable`: the system could not perform the trusted retrieval.

### Future availability upgrade

The packaged local BGE model is the current implementation. A future candidate
embedding model may be evaluated later, but it is not a simple provider switch:
it needs a separately indexed collection and the same
supported/no-evidence/grounding evaluation before it replaces the current
model. The customer path has no hidden provider fallback.

Build 09 acceptance evidence:

1. Simulated embedding failure never calls the answer LLM.
2. The public response exposes no unrelated sources or policy claims.
3. The customer receives a retriable/handoff response, not a false
   `no_evidence` conclusion.
4. Focused unit tests pass; the full regression suite is run before the build
   is accepted.

## 2. Expand the Knowledge Scope Before Advanced Retrieval

Build 10 expanded the project-owned demo corpus from five to 15 policy
sections, with 36 reviewed retrieval cases and 15 grounding contracts. Its
live vector baseline exposed a real abstention gap: no single cosine-distance
threshold retained all 28 supported cases while rejecting all 8 no-evidence
cases. See `docs/BUILD_10_POLICY_CORPUS_AND_EVALUATION_EXPANSION.md`.

Priority policy themes:

- returns, exchanges, shipping fees, refund timing, warranty and repair;
- order cancellation and address changes before shipment;
- delivery delay, lost/damaged shipment, and human handoff;
- invoices, price protection, coupons, membership, and explicit unsupported
  boundaries.

Every policy must be a reviewed demo business rule with a visible version or
source label. It must not be invented by the answer model.

The evaluation set includes supported questions, paraphrases, boundary
conditions, no-evidence questions, and adversarial "please promise/compensate"
requests. Future additions must remain reviewed, synthetic and non-personal.

## 3. Measure Answer Grounding Separately

After the existing retrieval/no-evidence calibration, add a small answer
grounding set. Each case records the expected source, allowed business facts,
forbidden high-risk claims, and whether no answer-model call is expected.

The evaluator is an offline/release gate, not a second model that rewrites each
customer answer at runtime. Deterministic checks and human review are primary;
an LLM judge, if used, is only supplementary.

## 4. Use the Simplest Retrieval That the Evidence Supports

Markdown is a document format and can be the source of a RAG system. It is not
the opposite of RAG.

- For a few short, exact, stable rules, direct deterministic rendering or a
  small fixed FAQ can be more accurate than generative RAG.
- Use RAG when natural-language questions must locate relevant evidence across
  a growing or changing document set.
- Use Java/API tools, not RAG, for live order state, logistics, inventory, or
  other transactional facts.

Build 11 addressed the current semantic-sufficiency gap with a structured,
server-validated evidence verifier. On the reviewed local set it retained
28/28 supported cases and rejected 8/8 no-evidence cases; full answer
grounding passed 15/15 hard contracts. This does not establish broad quality or
remove the need for a future A/B experiment.

Hybrid retrieval and reranking are not automatic upgrades. Implement them only
if a larger reviewed evaluation shows a remaining retrieval/ranking gap, then
compare evidence Recall@K, no-evidence safety, grounding review, latency, and
cost against the current vector-plus-verifier baseline.

## 5. Evaluation Harness Position

A test or evaluation harness is the surrounding runner that feeds reviewed
cases into the real module, captures privacy-safe outputs/traces, checks
expectations, and reports regressions. The project already has the beginning
of one through its Agent and RAG evaluation scripts. No separate "Harness"
framework is needed now; strengthen the project-owned evaluation runner when
the expanded corpus and grounding cases are built.
