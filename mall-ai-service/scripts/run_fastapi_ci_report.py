"""Run the deterministic FastAPI suite and emit a commit-bound report.

The XML contains pytest's machine-readable result.  The sidecar stores only
counts, test names, a semantic report hash and Git identity; it never stores
test input, prompts, credentials or customer data.  CI uploads both files so
the public-release validator can compare facts with the exact report produced
by the Python gate instead of trusting a historical number.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parent


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _runtime_commit() -> str:
    facts_path = REPOSITORY_ROOT / "docs" / "evidence" / "current-release-facts.json"
    try:
        facts = json.loads(facts_path.read_text(encoding="utf-8"))
        value = facts.get("runtimeCommit")
        if isinstance(value, str) and len(value) == 40:
            return value
    except (OSError, json.JSONDecodeError):
        pass
    return _commit()


def _parse_junit(path: Path) -> dict[str, object]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall(".//testsuite"))
    tests = sum(int(item.attrib.get("tests", "0")) for item in suites)
    failures = sum(int(item.attrib.get("failures", "0")) for item in suites)
    errors = sum(int(item.attrib.get("errors", "0")) for item in suites)
    skipped = sum(int(item.attrib.get("skipped", "0")) for item in suites)
    names = sorted(
        f"{case.attrib.get('classname', '')}.{case.attrib.get('name', '')}"
        for suite in suites
        for case in suite.findall("testcase")
    )
    semantic = json.dumps(
        {
            "tests": tests,
            "failures": failures,
            "errors": errors,
            "skipped": skipped,
            "names": names,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "tests": tests,
        "failures": failures,
        "errors": errors,
        "skipped": skipped,
        "passed": tests - failures - errors - skipped,
        "caseCount": len(names),
        "semanticReportSha256": hashlib.sha256(semantic).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junitxml", type=Path, default=Path("v3-fastapi-junit.xml"))
    parser.add_argument("--report", type=Path, default=Path("v3-fastapi-report.json"))
    args = parser.parse_args()
    junit_path = args.junitxml if args.junitxml.is_absolute() else ROOT / args.junitxml
    report_path = args.report if args.report.is_absolute() else ROOT / args.report
    junit_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", f"--junitxml={junit_path}"],
        cwd=ROOT,
        check=False,
    )
    counts = _parse_junit(junit_path)
    payload = {
        "schemaVersion": "mall-fastapi-test-report.v1",
        "repositoryCommit": _commit(),
        "runtimeCommit": _runtime_commit(),
        "junitSha256": _sha256(junit_path),
        **counts,
        "exitCode": result.returncode,
    }
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "fastapi_report "
        f"passed={payload['passed']} failed={payload['failures'] + payload['errors']} "
        f"skipped={payload['skipped']} exit={result.returncode} "
        f"semantic_sha256={payload['semanticReportSha256']}"
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
