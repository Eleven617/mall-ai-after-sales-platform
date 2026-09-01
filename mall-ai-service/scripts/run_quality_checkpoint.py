"""Run one explicit Build 17 quality checkpoint profile.

This script is intentionally separate from FastAPI. It never runs as part of a
customer request. Exit codes: 0 passed, 1 quality/budget failure, 2 provider or
local-environment blocked.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings  # noqa: E402
from app.services.agent_evaluation import (  # noqa: E402
    evaluate_agent_case,
    load_agent_evaluation_cases,
)
from app.services.diagnosis_evaluation import (  # noqa: E402
    evaluate_diagnosis_case,
    load_diagnosis_cases,
)
from app.services.quality_checkpoint import (  # noqa: E402
    CheckpointBudget,
    run_quality_checkpoint,
)
from app.services.rag_evaluation import evaluate_rag_cases, load_rag_cases  # noqa: E402
from app.services.rag_grounding_evaluation import (  # noqa: E402
    evaluate_rag_grounding_case,
    load_rag_grounding_cases,
)
from app.services.rag_verifier_evaluation import evaluate_rag_verifier_cases  # noqa: E402
from app.services.llm_observability import TokenPricing  # noqa: E402


PROFILE_CASE_FILES = {
    "offline-agent": "evals/agent_cases.json",
    "offline-diagnosis": "evals/diagnosis_cases.json",
    "rag-retrieval-local": "evals/rag_cases.json",
    "rag-verifier-live": "evals/rag_cases.json",
    "rag-grounding-live": "evals/rag_grounding_cases.json",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=sorted(PROFILE_CASE_FILES), required=True)
    parser.add_argument("--max-cases", type=int, default=None)
    parser.add_argument("--max-seconds", type=float, default=None)
    parser.add_argument("--llm-timeout-seconds", type=float, default=None)
    parser.add_argument("--llm-max-attempts", type=int, default=None)
    parser.add_argument("--input-token-price-per-million", type=float, default=None)
    parser.add_argument("--output-token-price-per-million", type=float, default=None)
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print the aggregate safe report only, without per-case entries.",
    )
    args = parser.parse_args()

    cases = _load_cases(args.profile)
    evaluator = _evaluator_for(args.profile)
    pricing = _pricing_from_args(args)
    budget = CheckpointBudget(
        max_cases=(
            args.max_cases
            if args.max_cases is not None
            else settings.quality_checkpoint_max_cases
        ),
        max_total_seconds=(
            args.max_seconds
            if args.max_seconds is not None
            else settings.quality_checkpoint_max_total_seconds
        ),
        llm_timeout_seconds=(
            args.llm_timeout_seconds
            if args.llm_timeout_seconds is not None
            else settings.quality_checkpoint_llm_timeout_seconds
        ),
        llm_max_attempts=(
            args.llm_max_attempts
            if args.llm_max_attempts is not None
            else settings.quality_checkpoint_llm_max_attempts
        ),
    )

    report = run_quality_checkpoint(
        checkpoint_name=args.profile,
        cases=cases,
        evaluate_case=evaluator,
        budget=budget,
        pricing=pricing,
        progress_listener=_print_progress,
    )
    printable_report = (
        {key: value for key, value in report.items() if key != "cases"}
        if args.summary
        else report
    )
    print(json.dumps(printable_report, ensure_ascii=False, indent=2))
    status = report["status"]
    if status == "passed":
        return 0
    if status == "environment_blocked":
        return 2
    return 1


def _load_cases(profile: str) -> list[dict[str, Any]]:
    path = PROJECT_ROOT / PROFILE_CASE_FILES[profile]
    if profile == "offline-agent":
        return load_agent_evaluation_cases(path)
    if profile == "offline-diagnosis":
        return load_diagnosis_cases(path)
    if profile == "rag-retrieval-local":
        return load_rag_cases(path)
    if profile == "rag-verifier-live":
        return load_rag_cases(path)
    return load_rag_grounding_cases(path)


def _evaluator_for(profile: str):
    if profile == "offline-agent":
        return evaluate_agent_case
    if profile == "offline-diagnosis":
        return evaluate_diagnosis_case
    if profile == "rag-retrieval-local":
        return _evaluate_retrieval_case
    if profile == "rag-verifier-live":
        return _evaluate_verifier_case
    return evaluate_rag_grounding_case


def _evaluate_retrieval_case(case: Mapping[str, Any]) -> dict[str, Any]:
    report = evaluate_rag_cases([dict(case)])
    result = report["results"][0]
    expected_section = result.get("expected_section")
    passed = (
        bool(result.get("evidence_hit"))
        if expected_section
        else bool(result.get("no_evidence_pass"))
    )
    return {
        # Raw retrieval is a candidate-stage measurement. For an unsupported
        # question, a close chunk is a review signal, not proof that the final
        # answer path is unsafe; Build 11's verifier profile is the safety gate.
        "passed": True if not expected_section else passed,
        "checks": (
            {"supported_evidence_hit": passed}
            if expected_section
            else {"candidate_retrieval_completed": True}
        ),
        "review_checks": {
            "no_evidence_candidate_rejected": (
                True if expected_section else bool(result.get("no_evidence_pass"))
            ),
        },
    }


def _evaluate_verifier_case(case: Mapping[str, Any]) -> dict[str, Any]:
    report = evaluate_rag_verifier_cases([dict(case)])
    result = report["cases"][0]
    if result.get("status") == "environment_blocked":
        return {"status": "environment_blocked", "observed": {"outcome": "evidence_verification_unavailable"}}
    passed = bool(result.get("passed"))
    return {
        "passed": passed,
        "checks": {"semantic_evidence_contract": passed},
    }


def _pricing_from_args(args: argparse.Namespace) -> TokenPricing | None:
    input_price = args.input_token_price_per_million
    output_price = args.output_token_price_per_million
    if (input_price is None) != (output_price is None):
        raise SystemExit(
            "Both token price arguments are required to calculate an estimate."
        )
    if input_price is None:
        return None
    if input_price < 0 or output_price < 0:
        raise SystemExit("Token prices cannot be negative.")
    return TokenPricing(input_per_million=input_price, output_per_million=output_price)


def _print_progress(event: dict[str, object]) -> None:
    print(
        "progress "
        f"{event['checkpoint']} "
        f"{event['completed_cases']}/{event['total_cases']} "
        f"attempted={event['attempted_cases']} "
        f"status={event['last_case_status']} "
        f"elapsed_ms={event['elapsed_ms']}",
        file=sys.stderr,
        flush=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
