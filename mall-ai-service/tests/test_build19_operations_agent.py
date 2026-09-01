from types import SimpleNamespace

import pytest

from app.schemas.operations import (
    CaseHandoffView,
    OperationsAnalysisDraft,
    OperationsMetrics,
)
from app.services.operations_agent import OperationsAnalysisError, analyze_case
from app.services.trace_service import InMemoryTraceSink, set_trace_sink_for_tests


def _case():
    return CaseHandoffView(
        case_id="12345678-1234-1234-1234-123456789abc",
        source_flow="customer_diagnosis",
        diagnosis_category="delivery_exception",
        evidence_status="insufficient",
        handoff_reason="insufficient_evidence",
        requires_human_review=True,
        case_status="OPEN",
        schema_version="1",
    )


def test_operations_agent_uses_one_model_call_and_the_human_selected_aggregate_window():
    calls = []
    metric_calls = []

    def generate_fn(**kwargs):
        calls.append(kwargs["response_model"])
        return SimpleNamespace(
            value=OperationsAnalysisDraft(
                summary="近期开启人工核实的配送异常需要关注。",
                risk_flags=[],
                recommended_human_attention=["复核配送异常案例"],
                limitations=["未包含仓储或承运商数据"],
            )
        )

    def metrics_fn(window_days, authorization):
        metric_calls.append((window_days, authorization))
        return OperationsMetrics(
            window_days=window_days,
            after_sales_by_status={"pending_review": 2},
            reason_counts={"质量问题": 1},
            outbox_by_status={"PUBLISHED": 2},
            delivery_by_status={"DELIVERED": 2},
        )

    result = analyze_case(
        case=_case(),
        authorization="Bearer operator-token",
        generate_fn=generate_fn,
        metrics_fn=metrics_fn,
    )

    assert calls == [OperationsAnalysisDraft]
    assert metric_calls == [(7, "Bearer operator-token")]
    assert result.draft.summary.startswith("近期开启")


def test_operations_agent_rejects_unapproved_window_before_query_or_model_call():
    with pytest.raises(OperationsAnalysisError):
        analyze_case(
            case=_case(),
            authorization="Bearer operator-token",
            preferred_window_days=14,
            generate_fn=lambda **_kwargs: (_ for _ in ()).throw(AssertionError("must not call model")),
            metrics_fn=lambda *_args: (_ for _ in ()).throw(AssertionError("must not query metrics")),
        )


def test_operations_agent_trace_contains_only_safe_lifecycle_metadata():
    sink = InMemoryTraceSink()
    set_trace_sink_for_tests(sink)
    try:
        analyze_case(
            case=_case(),
            authorization="Bearer operator-secret",
            generate_fn=lambda **_kwargs: SimpleNamespace(
                value=OperationsAnalysisDraft(
                    summary="仅根据聚合数据生成草稿。",
                    risk_flags=[],
                    recommended_human_attention=[],
                    limitations=["合成测试。"],
                )
            ),
            metrics_fn=lambda window_days, _authorization: OperationsMetrics(
                window_days=window_days,
                after_sales_by_status={"pending_review": 1},
                reason_counts={},
                outbox_by_status={},
                delivery_by_status={},
            ),
        )
    finally:
        set_trace_sink_for_tests(None)

    assert [event.flow for event in sink.events] == [
        "operations_analysis",
        "operations_analysis",
    ]
    assert sink.events[0].event == "run_started"
    assert sink.events[0].details == {}
    assert sink.events[1].event == "run_finished"
    assert sink.events[1].result_kind == "success"
    assert "operator-secret" not in " ".join(str(event) for event in sink.events)
