# Build 10: Policy Corpus and Evaluation Expansion

## Goal

Turn the original five-section RAG demo into a broader but still controlled
after-sales knowledge base. This build expands business coverage and the
evaluation contracts before considering any retrieval-architecture change such
as hybrid retrieval or reranking.

## Scope

The versioned demo policy corpus now contains 15 reviewed headings:

1. seven-day return;
2. return shipping fee;
3. exchange;
4. refund timing;
5. after-seven-day handling;
6. warranty and repair;
7. cancellation before shipment;
8. address changes;
9. delivery delay;
10. transport damage or loss;
11. return-method boundary;
12. invoice;
13. price protection;
14. coupons and compensation;
15. membership points.

The rules are explicitly labelled as project-owned demo rules, not a real
merchant's policy. Live deployment would require a reviewed business source
and an approval process for every policy update.

## Evaluation Coverage

- `evals/rag_cases.json`: 36 retrieval cases: 28 supported-policy questions
  and 8 no-evidence/induction questions.
- `evals/rag_grounding_cases.json`: 15 answer contracts: 12 supported-policy
  questions and 3 no-evidence questions.
- Questions cover paraphrases, policy boundaries, and requests that try to
  induce a promise such as guaranteed arrival, unconditional price protection,
  or automatic compensation.

When a policy explicitly rejects an extra benefit, a question about that
benefit is a **supported boundary case**, not a `no_evidence` case. The
no-evidence subset therefore contains only questions whose topic is absent
from this after-sales corpus. This keeps the evaluation oracle aligned with
the actual policy text.

## New Corpus Contract

`app/services/knowledge_contract.py` validates the local data before it is
re-indexed or evaluated. It checks that:

1. policy section titles are unique;
2. every supported retrieval case names an existing section;
3. every grounding case with an `answered` outcome names an existing source
   section;
4. every grounding case labelled `no_evidence` requires empty sources;
5. case IDs, questions and basic schema fields are valid.

Run the deterministic check with:

```powershell
.\.venv\Scripts\python.exe scripts\validate_policy_corpus.py
```

This is a data-integrity gate, not a quality score. It prevents a common
evaluation mistake: a test may look well-formed while referring to a policy
chapter that no longer exists after a document edit.

## Acceptance Status

Completed locally without external model calls:

- policy corpus expanded from 5 to 15 sections;
- retrieval and grounding evaluation data expanded from 11/6 to 36/15 cases;
- corpus contract is valid;
- focused deterministic tests pass.

Live Gemini measurement on 2026-08-04:

- the expanded 15-section corpus was successfully re-indexed into Chroma;
- at the inherited cosine-distance gate of `0.48`, vector retrieval kept the
  expected section in Top-3 for 28/28 supported cases;
- the same gate rejected 0/8 true no-evidence cases, so vector distance alone
  was not sufficient for customer-facing abstention;
- a threshold scan found no single distance value that both retained all 28
  supported cases and rejected all 8 no-evidence cases. At `0.24`, it retained
  26/28 supported cases and rejected 8/8 no-evidence cases; at `0.34`, it
  retained 28/28 but rejected only 5/8 no-evidence cases.

This is a measured retrieval trade-off, not a broad accuracy claim. It led to
the separate Build 11 semantic evidence-verification experiment rather than an
unmeasured hybrid-retrieval or reranking migration.
