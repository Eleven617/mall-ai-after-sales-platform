# RAG Evaluation Evidence - 2026-08-04

## Scope

This is a live vector-retrieval calibration for the reviewed local after-sales
knowledge base. It measures retrieval and the evidence gate only. It does not
measure generated-answer grounding, online LLM answer quality, latency, cost,
or production performance.

## Environment

- Embedding provider and model: Gemini `gemini-embedding-001`.
- Vector store: local Chroma collection with five policy chunks.
- Stored embedding dimension: 3072, matching the live provider response.
- Evaluation set: `evals/rag_cases.json`, 11 reviewed Chinese questions.
- Retrieval: Top-K = 3, Chroma cosine distance (lower is more relevant).
- Date: 2026-08-04.

## Baseline Finding

With the old threshold of 0.75:

- Supported policy questions: raw Recall@3 = 7/7 and evidence Recall@3 = 7/7.
- Unsupported questions: no-evidence pass rate = 0/4.

The four unsupported questions asked about return points, member points,
coupon compensation, and door-to-door collection. None is present in the
reviewed policy source, but their nearest irrelevant distances were 0.5761,
0.5975, 0.5267, and 0.5685. A 0.75 gate would pass all of them to the answer
model and create an avoidable unsupported-answer risk.

## Calibration Decision

The seven supported questions had nearest expected-policy distances from
0.1769 to 0.4243. The nearest unsupported query was 0.5267. A temporary live
run at 0.48 produced:

- Threshold-filtered evidence Recall@3: 7/7 = 1.00.
- No-evidence pass rate: 4/4 = 1.00.

The default `RAG_MAX_DISTANCE` is therefore set to 0.48. This preserves a
gap on both sides of the observed boundary while preferring refusal over an
unsupported policy answer.

## Resilience Follow-up

An end-to-end check also exercised the temporary vector-provider-unavailable
path. The original local lexical fallback could accept a body-only generic term
such as "can" from a question about coupon compensation, despite the policy
having no coupon rule. The fallback now requires a non-generic overlap with a
reviewed policy section title. This deliberately reduces fallback recall in
exchange for safe abstention; normal vector retrieval is unchanged.

## End-to-End User-Path Check

With the live embedding provider and answer model available, two generic,
non-personal test questions were run through `answer_after_sales_question`:

- A quality-related return-shipping-fee question returned a policy-grounded
  answer and one server-generated `退货运费` source.
- A coupon-compensation question returned the no-evidence handoff, with zero
  sources, and did not enter answer generation.

This verifies the local user-facing RAG path for these two cases. It remains
separate from a broader answer-grounding evaluation.

The deterministic Python regression suite passed 73 tests after the threshold
calibration and fallback-safety fix.

## Limits and Next Measurement

Eleven cases and five policy chunks are not enough to claim general RAG
accuracy. Before changing the threshold again or adding hybrid retrieval and
reranking, add reviewed paraphrases, adversarial near-miss questions, and new
policy sections. Then rerun the same evaluator and separately assess whether
the generated answer is grounded in the selected evidence.
