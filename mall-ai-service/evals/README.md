# Evaluation Sets

- `rag_cases.json` measures raw retrieval Recall@K and threshold-filtered
  evidence Recall@K against known after-sales policy sections. The current
  reviewed demo set has 36 questions (28 supported-policy and 8 no-evidence
  questions). It also records whether an unsupported question has no evidence
  that would reach the answer model. It does not claim answer correctness or
  live-model accuracy.
- `customer_service_cases.json` is the broad customer-service acceptance
  inventory for integration, safety, and workflow regression testing.
- `order_exception_cases.json` is the flagship after-sales workflow inventory.
  Each case explicitly says whether it is covered by offline unit tests or
  still requires a manual live run. It is an acceptance contract, not a claim
  that a real Java/Redis/model deployment has already passed.
- Run `python scripts/evaluate_rag.py` after ingesting the knowledge base and
  record the date, model, embedding provider, threshold, and result.
- The first recorded live vector calibration is
  `docs/RAG_EVALUATION_EVIDENCE_2026-08-04.md`; extend the reviewed set before
  treating its threshold as representative of a larger policy corpus.
- `rag_grounding_cases.json` and `scripts/evaluate_rag_grounding.py` evaluate
  source attribution, no-evidence behavior, forbidden high-risk claims, and
  fact-marker review signals. The current reviewed demo set has 15 answer
  contracts. Provider outages are reported separately from grounding-quality
  failures; see `docs/BUILD_09_RAG_RELIABILITY_AND_GROUNDING.md`.
- `scripts/evaluate_rag_verifier.py` runs the 36 retrieval cases through the
  semantic evidence verifier before final answer generation. It reports
  supported-policy retention and no-evidence rejection separately; see
  `docs/BUILD_11_SEMANTIC_EVIDENCE_VERIFICATION.md`.
- Run `scripts/validate_policy_corpus.py` before re-indexing or live RAG
  evaluation. It verifies that case IDs are unique and that expected policy
  sections still exist; it also validates the `chunk-v2` metadata contract.
  It is a structural gate, not an accuracy metric.
- `rag_chunk_metadata_cases.v1.json` is a separate eight-case synthetic
  structure/pre-filter suite. It covers version/date/category/language/type
  scoping, rule-condition-exception/table grouping, a filtered colloquial
  query and empty scope. Run `python scripts/evaluate_chunk_metadata.py
  --summary`; it is deterministic, local, and makes zero model calls. It does
  not replace the 52-case Dense ranking suite or live grounding checks.
- When a privacy-safe trace reveals a new failure or ambiguity, add a reviewed
  reproduction here, implement or adjust a deterministic test, then run the
  full regression suite before accepting the change. Do not store real tokens,
  customer messages, order numbers, or personal information in evaluation data.

## Build 17 Explicit Quality Checkpoints

`scripts/run_quality_checkpoint.py` runs one fixed profile only when a
developer or CI job invokes it. It is not imported by the customer API and it
does not create a reviewer UI or a per-request evaluation task.

- `--profile offline-agent`: six scripted custom-ReAct cases, zero provider calls.
- `--profile offline-diagnosis`: four scripted LangGraph cases, zero provider calls.
- `--profile rag-retrieval-local`: 36 local candidate-retrieval measurements.
  A close candidate for a no-evidence question becomes `review_required`; it
  must not be presented as a supported customer answer.
- `--profile rag-verifier-live`: 36 explicit DeepSeek semantic-evidence checks.
- `--profile rag-grounding-live`: 15 explicit end-to-end grounding contracts.

All profiles print case-by-case progress and safe aggregate metrics. Their
reports contain only fixture IDs, status, elapsed time, model-call counts,
provider usage when available, and optional caller-supplied cost estimates.
They exclude question text, model prose, policy text, tokens, order data and
credentials. Use `--summary` to avoid printing individual case rows in CI.

The live profiles have a separate total-time, provider-timeout, and retry cap;
they classify provider/network faults as `environment_blocked`, contract
violations as `quality_failed`, and candidate-stage gaps as `review_required`.
None of these outcomes changes a customer configuration automatically.

## Build 22 Unified After-sales Agent Reliability Suites

- `quality_agent_cases.v2.json` is the CI-safe `contract_mock` suite. It uses
  only repository-local synthetic inputs, scripted read-only tool plans,
  mocked tool results and mocked operations aggregates. It asserts approved
  tool order, step budget, duplicate-call blocking, no-evidence/tool-failure
  stops, schema/tool rejection, cross-account-safe outcomes, red-team handoff
  rejection and operations-number/window contracts. It does not connect to
  Redis pending state, Java, customer conversations, CaseHandoffs, production
  Trace or a model provider.
- `live_model_synthetic_cases.v1.json` is intentionally **not** a CI suite.
  It runs the real bounded model/graph only when a protected developer starts
  `live_model_synthetic`; its inputs, tool results and metrics remain
  versioned synthetic fixtures. It measures real prompt/tool-schema behavior
  without any customer or business write access. Provider unavailability is
  shown as an environment block, never silently counted as a quality pass.
- Existing durable-resume red-team tests live in
  `tests/test_durable_diagnosis.py`: owner mismatch, expiry/cancellation,
  version incompatibility, duplicate/replayed resume, concurrent resume lock
  and Redis failure all stop without an extra read or write.
