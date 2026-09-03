"""Validation for the versioned Mall v3.0 release-evaluation manifest.

The manifest is deliberately data rather than a Python list hidden in a test:
reviewers can inspect every synthetic case, its fixture hash, its executable
contract target and its public-safe summary without obtaining a model key or a
customer record.  This module validates the release inventory before CI runs
the ordinary test suites.  It does not claim that a registered browser/live
profile has run; those modes remain explicit manual gates.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MANIFEST_PATH = PROJECT_ROOT / "evals" / "v3" / "release-manifest.json"
EXPECTED_SUITE_VERSION = "mall-v3.0.release.v1"

# A release case belongs to exactly one category.  Historical pytest, RAG and
# quality-agent suites remain separate and therefore cannot be double-counted
# here just to inflate the v3.0 total.
CATEGORY_MINIMUMS: dict[str, int] = {
    "task_runtime": 80,
    "counterfactual_replan": 40,
    "candidate_resolution_critic": 36,
    "context_memory": 32,
    "skill_schema_scope": 64,
    "rag_v3": 80,
    "durable_async_recovery": 32,
    "java_mysql_integration": 30,
    "migration_cross_service_contract": 24,
    "browser_e2e": 24,
    "fault_injection": 36,
}
EXPECTED_DETERMINISTIC_TOTAL = sum(CATEGORY_MINIMUMS.values())
EXPECTED_LIVE_CASES = 36
EXPECTED_PERFORMANCE_PROFILES = 12

_CASE_ID = re.compile(r"^V3-[A-Z][A-Z0-9-]{5,79}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_SENSITIVE_MARKERS = (
    "bearer ",
    "token=",
    "api_key",
    "password",
    "order_sn",
    "raw_message",
    "rag_context",
    "traceback",
)
_FORBIDDEN_MANIFEST_KEYS = {"skip", "skipped", "disabled", "continueOnError", "allowFailure"}


class ReleaseManifestError(ValueError):
    """Raised when the static release inventory would make CI misleading."""


@dataclass(frozen=True)
class ReleaseManifestReport:
    suite_version: str
    deterministic_total: int
    category_counts: dict[str, int]
    live_case_total: int
    performance_profile_total: int
    case_set_sha256: str
    manifest_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "suiteVersion": self.suite_version,
            "deterministicTotal": self.deterministic_total,
            "categoryCounts": self.category_counts,
            "liveCaseTotal": self.live_case_total,
            "performanceProfileTotal": self.performance_profile_total,
            "caseSetSha256": self.case_set_sha256,
            "manifestSha256": self.manifest_sha256,
        }


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fixture_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def load_release_manifest(path: Path = DEFAULT_MANIFEST_PATH) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseManifestError("v3.0 release manifest 无法加载。") from exc
    if not isinstance(value, dict):
        raise ReleaseManifestError("v3.0 release manifest 顶层必须是对象。")
    return value


def validate_release_manifest(payload: Mapping[str, Any]) -> ReleaseManifestReport:
    _reject_forbidden_keys(payload)
    suite_version = _required_text(payload, "suiteVersion")
    if suite_version != EXPECTED_SUITE_VERSION:
        raise ReleaseManifestError("release manifest suiteVersion 不匹配。")
    raw_cases = _required_list(payload, "cases")
    raw_live_cases = _required_list(payload, "liveCases")
    raw_profiles = _required_list(payload, "performanceProfiles")

    case_ids: list[str] = []
    category_counts: Counter[str] = Counter()
    for raw_case in raw_cases:
        _validate_deterministic_case(raw_case, suite_version)
        case = _required_mapping(raw_case, "case") if "case" in raw_case else raw_case
        case_id = _required_text(case, "caseId")
        case_ids.append(case_id)
        category_counts[_required_text(case, "category")] += 1

    if len(case_ids) != len(set(case_ids)):
        raise ReleaseManifestError("release manifest 含重复 deterministic caseId。")
    if len(case_ids) != EXPECTED_DETERMINISTIC_TOTAL:
        raise ReleaseManifestError(
            f"release manifest deterministic case 数量必须为 {EXPECTED_DETERMINISTIC_TOTAL}。"
        )
    if set(category_counts) != set(CATEGORY_MINIMUMS):
        raise ReleaseManifestError("release manifest 分类集合不完整或存在未知分类。")
    for category, minimum in CATEGORY_MINIMUMS.items():
        if category_counts[category] < minimum:
            raise ReleaseManifestError(f"{category} 少于最小 {minimum} 条 case。")

    _validate_live_cases(raw_live_cases, suite_version)
    _validate_performance_profiles(raw_profiles)
    integrity = _required_mapping(payload, "integrity")
    actual_case_set = fixture_hash(sorted(case_ids))
    expected_case_set = _required_text(integrity, "caseSetSha256")
    if expected_case_set != actual_case_set:
        raise ReleaseManifestError("release manifest case 集合摘要不匹配。")
    manifest_copy = dict(payload)
    manifest_copy.pop("integrity", None)
    manifest_digest = fixture_hash(manifest_copy)
    expected_manifest_digest = _required_text(integrity, "manifestSha256")
    if expected_manifest_digest != manifest_digest:
        raise ReleaseManifestError("release manifest 内容摘要不匹配。")
    return ReleaseManifestReport(
        suite_version=suite_version,
        deterministic_total=len(case_ids),
        category_counts=dict(sorted(category_counts.items())),
        live_case_total=len(raw_live_cases),
        performance_profile_total=len(raw_profiles),
        case_set_sha256=actual_case_set,
        manifest_sha256=manifest_digest,
    )


def _validate_deterministic_case(raw_case: Any, suite_version: str) -> None:
    case = _required_mapping(raw_case, "case") if isinstance(raw_case, Mapping) and "case" in raw_case else _required_mapping_value(raw_case)
    if _required_text(case, "suiteVersion") != suite_version:
        raise ReleaseManifestError("deterministic case suiteVersion 不一致。")
    case_id = _required_text(case, "caseId")
    if not _CASE_ID.fullmatch(case_id):
        raise ReleaseManifestError("deterministic caseId 格式不合法。")
    category = _required_text(case, "category")
    if category not in CATEGORY_MINIMUMS:
        raise ReleaseManifestError("deterministic case 分类不在 release contract 内。")
    tags = _required_list(case, "tags")
    if not all(isinstance(tag, str) and tag.strip() for tag in tags):
        raise ReleaseManifestError("deterministic case tags 不合法。")
    for key in ("goal", "fixtureRef", "injectedEvent", "safeSummary", "executionTarget"):
        _safe_text(_required_text(case, key), field=key)
    fixture = _required_mapping(case, "fixture")
    expected_fixture_hash = _required_text(case, "fixtureHash")
    if not _SHA256.fullmatch(expected_fixture_hash) or expected_fixture_hash != fixture_hash(fixture):
        raise ReleaseManifestError("deterministic case fixtureHash 不匹配。")
    initial_state = _required_mapping(case, "initialState")
    if not initial_state:
        raise ReleaseManifestError("deterministic case initialState 不能为空。")
    outcome = _required_mapping(case, "requiredOutcome")
    _safe_text(_required_text(outcome, "status"), field="requiredOutcome.status")
    assertions = _required_list(outcome, "assertions")
    if not assertions or not all(isinstance(value, str) and value.strip() for value in assertions):
        raise ReleaseManifestError("deterministic case 必须有可执行 assertions。")
    forbidden_effects = _required_list(case, "forbiddenEffects")
    evidence = _required_list(case, "expectedEvidence")
    if not forbidden_effects or not evidence:
        raise ReleaseManifestError("deterministic case 缺少副作用或证据断言。")
    failure_code = case.get("expectedFailureCode")
    if failure_code is not None and (not isinstance(failure_code, str) or not re.fullmatch(r"[a-z][a-z0-9_]{1,79}", failure_code)):
        raise ReleaseManifestError("deterministic case failure code 不合法。")
    budget = _required_mapping(case, "budget")
    for key in ("maxModelCalls", "maxToolCalls", "maxWallClockSeconds"):
        value = budget.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ReleaseManifestError("deterministic case budget 不合法。")


def _validate_live_cases(cases: list[Any], suite_version: str) -> None:
    if len(cases) != EXPECTED_LIVE_CASES:
        raise ReleaseManifestError(f"live case 数量必须为 {EXPECTED_LIVE_CASES}。")
    seen: set[str] = set()
    for item in cases:
        case = _required_mapping_value(item)
        case_id = _required_text(case, "caseId")
        if case_id in seen or not _CASE_ID.fullmatch(case_id):
            raise ReleaseManifestError("live caseId 重复或格式不合法。")
        seen.add(case_id)
        if _required_text(case, "suiteVersion") != suite_version:
            raise ReleaseManifestError("live case suiteVersion 不一致。")
        if case.get("mode") != "manual_live_synthetic":
            raise ReleaseManifestError("live case 只能是显式手工合成模式。")
        fixture = _required_mapping(case, "fixture")
        if _required_text(case, "fixtureHash") != fixture_hash(fixture):
            raise ReleaseManifestError("live case fixtureHash 不匹配。")
        budget = _required_mapping(case, "budget")
        for key in ("maxModelCalls", "maxToolCalls", "maxWallClockSeconds"):
            if not isinstance(budget.get(key), int) or budget[key] < 1:
                raise ReleaseManifestError("live case budget 不合法。")
        if case.get("requiredRuns") != 3:
            raise ReleaseManifestError("live case 必须要求三次独立运行。")
        _safe_text(_required_text(case, "safeSummary"), field="live.safeSummary")


def _validate_performance_profiles(profiles: list[Any]) -> None:
    if len(profiles) != EXPECTED_PERFORMANCE_PROFILES:
        raise ReleaseManifestError(f"performance profile 数量必须为 {EXPECTED_PERFORMANCE_PROFILES}。")
    profile_ids: set[str] = set()
    for item in profiles:
        profile = _required_mapping_value(item)
        profile_id = _required_text(profile, "profileId")
        if profile_id in profile_ids or not re.fullmatch(r"v3-profile-[a-z0-9-]{3,48}", profile_id):
            raise ReleaseManifestError("performance profileId 重复或格式不合法。")
        profile_ids.add(profile_id)
        if profile.get("mode") not in {"contract_mock", "manual_live_synthetic", "manual_compose"}:
            raise ReleaseManifestError("performance profile mode 不合法。")
        _safe_text(_required_text(profile, "safeSummary"), field="profile.safeSummary")


def _reject_forbidden_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in _FORBIDDEN_MANIFEST_KEYS:
                raise ReleaseManifestError("release manifest 不允许 skip/allow-failure 开关。")
            _reject_forbidden_keys(item)
    elif isinstance(value, list):
        for item in value:
            _reject_forbidden_keys(item)


def _safe_text(value: str, *, field: str) -> None:
    lowered = value.lower()
    if len(value) > 800 or any(marker in lowered for marker in _SENSITIVE_MARKERS):
        raise ReleaseManifestError(f"release manifest {field} 含不允许的敏感文本。")
    if re.search(r"(?<!\d)\d{10,}(?!\d)", value):
        raise ReleaseManifestError(f"release manifest {field} 不能含完整业务标识。")


def _required_mapping(value: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    return _required_mapping_value(value.get(key))


def _required_mapping_value(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReleaseManifestError("release manifest 缺少对象字段。")
    return value


def _required_list(value: Mapping[str, Any], key: str) -> list[Any]:
    item = value.get(key)
    if not isinstance(item, list):
        raise ReleaseManifestError(f"release manifest 缺少列表字段：{key}。")
    return item


def _required_text(value: Mapping[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ReleaseManifestError(f"release manifest 缺少文本字段：{key}。")
    return item.strip()
