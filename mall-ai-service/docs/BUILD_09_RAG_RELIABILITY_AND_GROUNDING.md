# Build 09: RAG Reliability and Grounding Contracts

## Goal

Turn two RAG quality decisions into executable behavior and repeatable
evidence:

1. Trusted retrieval failure must fail closed rather than use an unmeasured
   lexical answer fallback.
2. A policy answer must be evaluated separately from retrieval quality.

## Delivered Behavior

`RagAnswer` now distinguishes three customer-safe states:

- `no_evidence`: vector retrieval completed, but no chunk passed the configured
  distance threshold;
- `retrieval_unavailable`: trusted embedding/vector retrieval could not run;
- `answer_generation_unavailable`: evidence was found, but the answer provider
  could not generate the explanation.

For the latter two states, the policy answer model is not trusted to invent a
replacement. The return workflow preserves a verified draft, creates no return
proposal, and never reaches a Java write call until policy retrieval and answer
generation are available again.

## Grounding Evaluation

`evals/rag_grounding_cases.json` contains six reviewed, non-personal policy
questions: four supported-policy questions and two no-evidence questions.

The evaluator has two layers:

- Hard checks: expected outcome, source presence/absence, expected source
  section, and forbidden high-risk claims.
- Review signals: expected fact marker groups. They help a reviewer spot a
  missing fact, but a harmless paraphrase such as "you pay" instead of
  "customer pays" does not create a false hard failure.

Provider outages are reported as `environment_blocked`, not as grounding
quality failures. The evaluator intentionally does not emit raw customer
messages, credentials, or arbitrary live answers in its report.

## Verification

Focused deterministic tests cover fail-closed retrieval, generation outage
distinction, return-write blocking, hard grounding failures, review-marker
normalization, and provider-outage classification.

A live run on 2026-08-04 using generic, non-personal questions passed:

- hard grounding contracts: 6/6;
- fact-marker review signals: 6/6;
- environment-blocked cases: 0.

This does not establish broad answer accuracy. It is a small policy corpus and
six-case local evidence set. The next RAG scope is to expand reviewed policies
and cases, then measure whether hybrid retrieval or reranking provides a real
gain.
