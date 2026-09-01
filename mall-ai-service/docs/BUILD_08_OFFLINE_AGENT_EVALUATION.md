# Build 08: Offline Agent Evaluation Runner

## Goal

Provide a repeatable, privacy-safe baseline for evaluating the existing
read-only Agent control loop before adding a multi-tool diagnosis feature or
considering LangGraph.

## What It Runs

`evals/agent_cases.json` contains only reviewed synthetic inputs, scripted
model responses, synthetic tool results, and deterministic expectations.  The
runner patches the model and tool boundary, then runs the real
`run_agent_result()` control flow.

```text
synthetic case
  -> scripted model/tool boundary
  -> real Agent loop and trace logic
  -> process checks + result checks
  -> JSON report
```

Run it from `mall-ai-service`:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_agent.py
```

The process report includes only safe metadata: tool names, trace event names,
step count, fact-card source names, and pending-tool name.  It excludes user
messages, tool arguments, raw tool results, model text, tokens, and
credentials.

## Current Coverage

1. Trusted logistics facts replace a hallucinated model conclusion.
2. A missing order number becomes a pending task without executing the tool.
3. A write-style tool call is blocked by the Agent's read-only allow-list.
4. The same tool call is stopped before the second execution.
5. A model business conclusion without a tool result is rejected.
6. Model-provider failure produces a controlled fallback.

## Boundaries

This is an **offline scripted** evaluation, not a live-model benchmark.  A
passing report proves the deterministic Agent guardrails and response boundary
for the represented cases.  It does not prove online tool-selection accuracy,
Gemini vector-retrieval quality, browser behavior, or production deployment.

Before any live Gemini/vector RAG evaluation, ask the learner to enable the
required VPN/proxy and record provider availability separately from retrieval
quality.
