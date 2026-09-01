# Workflow Evaluation and Reviewed Feedback

## Purpose

The AI service may help identify a failure pattern, but it must not silently
change a business rule, authorization boundary, policy document, or live code.
Every iteration becomes a reviewed regression case first.

## Evidence Sources

1. `evals/order_exception_cases.json` records the expected behavior for the
   flagship after-sales workflow.
2. Deterministic unit tests simulate Java, RAG, and model boundaries so the
   workflow can be checked without a real customer account or live model call.
3. `trace_service` logs only an allow-listed set of metadata: step count, tool
   name, boolean field-presence flags, product-option count, and policy-source
   count. Session IDs are hashed; tokens, raw messages, order IDs, prices,
   receiver data, tool arguments, and model responses are never trace fields.

## Reference-Inspired Evaluation Design

The external `ecom-service-agent` project separates process metrics from result
metrics and uses an isolated sandbox to make offline runs reproducible. We will
adopt that idea in our own implementation after real Java authentication is
verified:

- Process: route/tool accuracy, missing-argument behavior, repeated-call
  prevention, step/latency/token budgets, and authorization-block events.
- Result: verified-fact consistency, RAG evidence sufficiency, refusal behavior,
  proposal/confirmation correctness, and end-to-end workflow completion.
- Live boundary: offline mocks remain fast regression tests; a separate
  disposable-account manual suite proves Java, Redis, browser, and model
  integration. Passing mocks is never reported as production verification.
- LLM Judge: optional explanatory signal only. Deterministic authorization,
  write-operation, and fact-source checks remain acceptance gates.

## Reviewed Feedback Loop

```text
privacy-safe trace or manual test observation
    -> human decides whether it is a real product failure
    -> create a sanitized reproduction in evals/
    -> AI may propose tests or a patch
    -> human reviews security and business impact
    -> run the full unit suite
    -> manually rerun the affected live case before release
```

## Rules That Never Self-Modify

- JWT authorization and order/item ownership checks
- Java write request fields and duplicate-application rules
- confirmation requirement and proposal expiration
- policy knowledge-base publishing
- trace allow-list and sensitive-data handling

## Current Status

Offline workflow regression is covered by the Python test suite. The
`manual_live` case in `order_exception_cases.json` remains pending until the
Java service, Redis, model provider, and frontend are started together.
