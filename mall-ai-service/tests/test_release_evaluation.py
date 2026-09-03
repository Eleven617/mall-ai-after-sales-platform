"""Tests for the v3.0 deterministic release evaluator."""
from __future__ import annotations

from copy import deepcopy

import pytest

from app.runtime.release_evaluation import run_release_evaluation
from app.runtime.release_manifest import DEFAULT_MANIFEST_PATH, ReleaseManifestError, load_release_manifest


def test_release_evaluation_runs_every_registered_case_and_runtime_smokes() -> None:
    report = run_release_evaluation()

    assert report.suite_version == "mall-v3.0.release.v1"
    assert report.registered_total == 478
    assert report.registered_passed == 478
    assert report.representative_total == 8
    assert report.representative_passed == 8
    assert report.failed == 0
    assert all(case.status == "PASSED" for case in report.cases)


def test_release_evaluation_keeps_invalid_decision_failures_visible(tmp_path) -> None:
    payload = load_release_manifest(DEFAULT_MANIFEST_PATH)
    payload = deepcopy(payload)
    payload["cases"][0]["requiredOutcome"]["assertions"].append("unknown_assertion")
    # The integrity digest must be recomputed by the producer; a stale digest
    # is intentionally a hard manifest failure rather than a soft warning.
    path = tmp_path / "tampered-manifest.json"
    path.write_text(__import__("json").dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ReleaseManifestError, match="摘要"):
        run_release_evaluation(path)
