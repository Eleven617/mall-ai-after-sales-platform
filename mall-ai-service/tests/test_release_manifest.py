"""Deterministic integrity tests for the v3.0 release inventory."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from app.runtime.release_manifest import (
    CATEGORY_MINIMUMS,
    DEFAULT_MANIFEST_PATH,
    ReleaseManifestError,
    load_release_manifest,
    validate_release_manifest,
)


def _manifest() -> dict:
    return load_release_manifest(DEFAULT_MANIFEST_PATH)


def test_release_manifest_has_reviewed_inventory_and_integrity_digests() -> None:
    report = validate_release_manifest(_manifest())

    assert report.suite_version == "mall-v3.0.release.v1"
    assert report.deterministic_total == 478
    assert report.live_case_total == 36
    assert report.performance_profile_total == 12
    assert report.category_counts == CATEGORY_MINIMUMS
    assert len(report.case_set_sha256) == 64
    assert len(report.manifest_sha256) == 64


def test_manifest_rejects_duplicate_case_ids_instead_of_recounting_them() -> None:
    payload = _manifest()
    payload["cases"] = deepcopy(payload["cases"])
    payload["cases"][1]["caseId"] = payload["cases"][0]["caseId"]

    with pytest.raises(ReleaseManifestError, match="重复"):
        validate_release_manifest(payload)


def test_manifest_rejects_fixture_mutation_even_when_shape_stays_valid() -> None:
    payload = _manifest()
    payload["cases"] = deepcopy(payload["cases"])
    payload["cases"][0]["fixture"]["variation"] = "tampered"

    with pytest.raises(ReleaseManifestError, match="fixtureHash"):
        validate_release_manifest(payload)


def test_manifest_rejects_skip_or_allow_failure_controls() -> None:
    payload = _manifest()
    payload["cases"] = deepcopy(payload["cases"])
    payload["cases"][0]["skip"] = True

    with pytest.raises(ReleaseManifestError, match="skip"):
        validate_release_manifest(payload)


def test_manifest_rejects_empty_executable_assertions() -> None:
    payload = _manifest()
    payload["cases"] = deepcopy(payload["cases"])
    payload["cases"][0]["requiredOutcome"]["assertions"] = []

    with pytest.raises(ReleaseManifestError, match="assertions"):
        validate_release_manifest(payload)
