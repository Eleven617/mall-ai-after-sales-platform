# Build 17: Quality Checkpoints and Bounded Model Evaluation

## Status

Built and unit-tested. The new checkpoint runner was exercised locally and
against the live DeepSeek provider. It is a developer/CI command, not part of
the customer request path.

## Problem Solved

Earlier evaluation commands could run a large fixed set with little progress
visibility. A slow provider or network outage could look like a quality bug,
and a quality mismatch could be hidden inside an undifferentiated exception.
Build 17 adds a finite budget and reports the difference explicitly.

## Request/Execution Flow

```text
Developer/CI starts one profile
  -> load the reviewed fixture set
  -> run one case at a time
  -> record case ID, status, elapsed time and safe failed-check names
  -> collect opt-in LLM latency/retry/token metrics
  -> stop at case/time budget
  -> return passed / review_required / quality_failed / environment_blocked
```

No Vue request, FastAPI customer route, Redis state, Java token or customer
message enters this flow.

## Profiles

| Profile | Provider calls | Purpose |
| --- | ---: | --- |
| `offline-agent` | 0 | Six scripted custom-ReAct process/result cases. |
| `offline-diagnosis` | 0 | Four scripted LangGraph diagnosis cases. |
| `rag-retrieval-local` | 0 cloud calls | 36 local candidate-retrieval measurements. A close no-evidence candidate is a `review_required` signal, not proof of policy support. |
| `rag-verifier-live` | Explicit DeepSeek | 36 semantic evidence contracts after candidate retrieval. |
| `rag-grounding-live` | Explicit DeepSeek | 15 final answer grounding contracts. |

Example:

```powershell
.venv\Scripts\python.exe scripts\run_quality_checkpoint.py `
  --profile offline-agent --summary
```

Live profiles accept `--max-seconds`, `--llm-timeout-seconds`,
`--llm-max-attempts`, and optional current token prices. `--summary` avoids
printing individual case rows while retaining progress and aggregate metrics.

## Evidence From This Build

- Full Python regression: `148/148`; Vue production build passed; the rebuilt
  Docker stack and website-proxy customer smoke both returned healthy/`200`.
- Offline Agent: `6/6` passed; zero model calls.
- Offline LangGraph diagnosis: `4/4` passed; zero model calls.
- Local retrieval baseline: all `28/28` supported-policy cases reached the
  candidate evidence gate; five no-evidence questions produced a close
  candidate and are correctly marked `review_required`. This is why raw
  Recall@K is not the final safety metric.
- Live semantic verifier: `36/36` passed in `28.579s`; `33` DeepSeek calls,
  `22,198` total tokens, average call latency `823.45ms`, P95 `1,078ms`.
- Live grounding contracts: all `15/15` hard contracts passed. One
  wording-only review signal made its runner status `review_required`; no hard
  quality failure or environment block occurred. The existing manual-review
  boundary remains intentional.

These are local reviewed-set measurements, not production accuracy, latency,
cost, or SLA claims. The live runs did not configure a token price, so no cost
number is claimed.

## Failure Semantics

- `passed`: the case contract passed.
- `review_required`: the run completed, but a candidate-stage or wording
  signal needs human review; it is not silently called a pass.
- `quality_failed`: the provider completed but a hard reviewed contract failed.
- `environment_blocked`: network, timeout, provider configuration, local model,
  or provider availability prevented evaluation.
- `budget_exhausted`: remaining cases were not started; they are not failures.

The normal runtime uses a no-op LLM metric sink. No report is persisted by
default, and no checkpoint result changes prompts, policies, thresholds,
authorization, or production code automatically.

## Key Files

- `app/services/quality_checkpoint.py`: bounded case runner and status model.
- `app/services/llm_observability.py`: opt-in, in-memory latency/token/cost
  aggregation and temporary call policy.
- `app/services/llm_service.py`: emits only safe metrics and honors the
  checkpoint-only timeout/retry cap.
- `scripts/run_quality_checkpoint.py`: explicit offline/local-live entrypoint.
- `docs/BUILD_17_REQUIREMENTS_ALIGNMENT.md`: approved visibility and scope
  contract.
