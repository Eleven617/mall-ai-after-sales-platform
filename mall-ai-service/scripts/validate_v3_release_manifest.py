"""Validate the checked-in v3.0 release manifest without external services."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

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
        report = validate_release_manifest(load_release_manifest(args.manifest))
    except ReleaseManifestError as exc:
        print(f"v3_release_manifest FAILED: {exc}", file=sys.stderr)
        return 1
    payload = report.as_dict()
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(
            "v3_release_manifest PASSED "
            f"suite={report.suite_version} deterministic={report.deterministic_total} "
            f"live={report.live_case_total} profiles={report.performance_profile_total}"
        )
        print(json.dumps(report.category_counts, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
