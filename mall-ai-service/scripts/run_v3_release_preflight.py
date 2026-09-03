"""Run the deterministic Mall v3.0 release preflight.

This command is intentionally dependency-light and model-free.  It validates
the checked-in release inventory and executes the deterministic registry plus
the small real-runtime safety smoke set.  Live-model, browser, Java and
Compose profiles remain separate explicit gates and are never silently
represented as passing here.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.runtime.release_evaluation import run_release_evaluation  # noqa: E402
from app.runtime.release_manifest import (  # noqa: E402
    DEFAULT_MANIFEST_PATH,
    ReleaseManifestError,
    load_release_manifest,
    validate_release_manifest,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    try:
        manifest_report = validate_release_manifest(load_release_manifest(args.manifest))
        evaluation = run_release_evaluation(args.manifest)
    except ReleaseManifestError as exc:
        print(f"v3_release_preflight FAILED: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError) as exc:
        print(f"v3_release_preflight FAILED: {type(exc).__name__}", file=sys.stderr)
        return 1

    payload = {
        "suiteVersion": manifest_report.suite_version,
        "deterministicRegistered": evaluation.registered_total,
        "deterministicPassed": evaluation.registered_passed,
        "representativeRegistered": evaluation.representative_total,
        "representativePassed": evaluation.representative_passed,
        "failed": evaluation.failed,
        "caseSetSha256": manifest_report.case_set_sha256,
        "manifestSha256": manifest_report.manifest_sha256,
    }
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(
            "v3_release_preflight "
            f"{'PASSED' if evaluation.failed == 0 else 'FAILED'} "
            f"deterministic={evaluation.registered_passed}/{evaluation.registered_total} "
            f"representative={evaluation.representative_passed}/{evaluation.representative_total}"
        )
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if evaluation.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
