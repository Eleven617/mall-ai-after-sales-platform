# Structured Output Gateway Spike

## Status

**Built and offline unit-tested on 2026-08-12.** This is an isolated
capability module. It is not yet wired into customer routes, the after-sales
write workflow, RAG evidence verification, or the LangGraph diagnosis graph.
No live provider call was made for this spike.

## Problem

The existing JSON path is:

```text
Prompt asks for JSON -> remove Markdown fence -> json.loads -> each caller validates separately
```

It works, but JSON delivery mode and strict schema enforcement are not
centralized. A model can return extra fields, wrong scalar types, or an
undeclared enum value. Prompt wording alone cannot make those cases impossible.

## What Was Added

`app/services/structured_output_gateway.py` provides one boundary that:

1. appends the Pydantic model's JSON Schema to the model-facing output contract;
2. selects either `prompt_json` (the current behavior) or provider
   `json_object` mode;
3. parses through the existing LLM layer;
4. runs `model_validate(..., strict=True, extra="forbid")` before returning a
   typed object to business code.

`app/services/llm_service.py` now accepts an optional `output_mode` on
`generate_json()`:

- `prompt_json`: no change to the existing request payload;
- `json_object`: adds `response_format: {"type": "json_object"}` to the
  OpenAI-compatible request payload.

This is **not** OpenAI native `json_schema + strict: true`, and it is not
claimed to be DeepSeek Beta Strict Function Calling. The provider's actual
support must be verified by a deliberate live capability test before any route
is migrated.

## What This Solves

| Failure type | Gateway result |
| --- | --- |
| Markdown or non-JSON output | `generate_json()` fails safely instead of passing text onward. |
| Extra `debug` / invented fields | rejected by `extra="forbid"`. |
| `"true"` instead of boolean `true`, number instead of string | rejected by `strict=True`. |
| invented tool or enum name | rejected by the Pydantic Literal / enum contract. |
| model claims an order belongs to a user | **not solved here**; Java authorization still decides. |
| model invents a policy conclusion | **not solved here**; RAG evidence verification still decides. |

## Offline Evidence

`tests/test_structured_output_gateway.py` verifies:

1. the schema is supplied to the model-facing contract;
2. valid output becomes a typed Pydantic object;
3. extra fields, wrong scalar types and invented enum values are rejected;
4. `json_object` adds the provider request flag;
5. the historical `prompt_json` request shape remains unchanged;
6. an unknown delivery mode fails before contacting a provider.

These are deterministic unit tests. They are not a measurement of DeepSeek's
online JSON reliability and not production evidence.

## Recommended Mainline Upgrade

Do not replace every JSON call at once. Use this sequence:

1. **Capability probe:** with DeepSeek available, replay a small reviewed set
   of intent, return-extraction and evidence-verdict prompts using
   `prompt_json` versus `json_object`. Record JSON parse rate, strict schema
   pass rate, retry rate, latency and token usage. This does not need Gemini or
   VPN; it calls DeepSeek only.
2. **Contract tightening:** set `extra="forbid"` on the intended business
   response models, then ensure defaults and nullable fields are intentional.
   Do not make every field required merely to satisfy a schema; a multi-turn
   return draft legitimately has missing fields.
3. **One low-risk migration:** route the RAG evidence verifier through the
   gateway first. Its output is a small boolean-plus-source-ID contract and it
   already fails closed on an invalid verdict.
4. **Second migration:** move return-information extraction through the
   gateway. Keep the current evidence-span grounding and conservative order-ID
   extractor; structured output never makes an extracted fact trustworthy by
   itself.
5. **Third migration:** move intent routing and native tool-call parsing. Keep
   the tool allow-list, required-argument checks, Java ownership verification
   and confirmation gate unchanged.
6. **Strict Function Calling decision:** only after a provider-specific live
   probe proves compatible endpoint, schema restrictions, errors and measured
   benefit. If it works, use it for read-only tool argument shape; do not use
   it as permission to expose write endpoints directly to the model.

## Project Impact

The immediate code impact is deliberately zero for customers: no visible UI
change and no existing route behavior changes. The future impact is a shared,
testable LLM-to-service boundary that reduces format-related incidents and
makes JSON reliability measurable rather than anecdotal.

It strengthens the project's engineering story without replacing its real
highlights:

```text
Structured-output contract
  + RAG evidence validation
  + Java identity / order ownership validation
  + explicit confirmation before write
  = a controlled, explainable after-sales AI workflow
```

## Non-Claims

- Not a claim that the current project uses provider-native strict JSON Schema.
- Not a claim that JSON mode improves business accuracy until measured.
- Not a replacement for Java permissions, RAG grounding, Redis state, or write
  idempotency.
