"""Validate public release facts, README references and safety boundaries.

This is deliberately deterministic: it never calls a model, Docker, GitHub or a
business API.  It checks that the public surface agrees with the checked-in
facts source and that ignored local evidence cannot accidentally be committed.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FACTS_PATH = ROOT / "docs" / "evidence" / "current-release-facts.json"
README_PATH = ROOT / "README.md"
HISTORY_MARKER = "## 历史审计记录"


def fail(message: str) -> None:
    raise SystemExit(f"public_release_validation FAILED: {message}")


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True)
    if result.returncode != 0:
        fail(f"git {' '.join(args)} exited {result.returncode}: {result.stderr.strip()}")
    return result.stdout.strip()


def current_section(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return text.split(HISTORY_MARKER, 1)[0]


def main() -> int:
    require(FACTS_PATH.is_file(), "current-release-facts.json is missing")
    try:
        facts = json.loads(FACTS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"facts cannot be parsed: {exc}")

    readme = README_PATH.read_text(encoding="utf-8")
    main_eval = facts["mainEvaluation"]
    supplemental = facts["supplementalEvaluation"]
    tests = facts["tests"]
    field = tests["fieldAcceptance"]
    ci = facts["ci"]

    for key in ("schemaVersion", "runtimeCommit", "evidenceCommit", "publicClaims", "prohibitedClaims", "upstreamBoundary"):
        require(key in facts, f"facts missing {key}")
    require(re.fullmatch(r"[0-9a-f]{40}", facts["runtimeCommit"]) is not None, "runtimeCommit must be a full SHA")
    require(main_eval["passed"] == main_eval["executed"] == 72, "main evaluation facts mismatch")
    require(supplemental["passed"] == supplemental["executed"] == 36, "supplemental evaluation facts mismatch")
    require(supplemental["independentBlindSet"] is False, "supplemental set must not be declared blind")
    require(tests["fastapi"]["passed"] == 365 and tests["fastapi"]["failed"] == 0, "FastAPI facts mismatch")
    require(tests["java"]["portalCore"] == "12/12", "Java portal core fact mismatch")
    require(tests["java"]["portalCompatibility"] == "2/2", "Java portal compatibility fact mismatch")
    require(tests["java"]["admin"] == "6/6", "Java admin fact mismatch")
    require(tests["java"]["springContext"] == "1/1", "Spring context fact mismatch")
    require(field["total"] == "122/122" and field["failed"] == field["environmentBlocked"] == 0, "field facts mismatch")

    forbidden_phrases = (
        "## 评测发现与改进方向",
        "portal `14/14`",
        "portal 14/14",
        "独立合成 holdout",
        "独立合成 Holdout",
        "独立 12 Case",
        "独立12 Case",
        "各 `52/52`",
        "各52/52",
        "52/52 全部通过",
    )
    for phrase in forbidden_phrases:
        require(phrase not in readme, f"README contains forbidden public wording: {phrase}")
    required_fragments = (
        "DeepSeek",
        "72/72",
        "补充评测集",
        "36/36",
        "Grounding",
        "15/15",
        "57/57",
        "portal 核心 `12/12`",
        "admin `6/6`",
        "Spring context `1/1`",
        "478/478",
        "122/122",
        "365 passed",
        "MRR `0.948718`",
        "nDCG@3 `0.962147`",
    )
    for fragment in required_fragments:
        require(fragment in readme, f"README missing fact fragment: {fragment}")
    require("不是独立盲测集" in readme, "README must disclose supplemental-set boundary")
    require(
        re.search(r"52/52.{0,20}(准确率|全部通过)|(?:准确率|全部通过).{0,20}52/52", readme) is None,
        "README must not present retrieval as a 52/52 accuracy/pass claim",
    )

    # Validate local Markdown links and image references used by the README.
    references = re.findall(r"!\[[^]]*\]\(([^)]+)\)|\[[^]]+\]\(([^)]+)\)", readme)
    image_hashes: set[str] = set()
    local_images: list[Path] = []
    for image_ref, link_ref in references:
        ref = image_ref or link_ref
        if not ref or "://" in ref or ref.startswith("#"):
            continue
        path = (ROOT / ref.split("#", 1)[0]).resolve()
        require(path.is_file(), f"README reference missing: {ref}")
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
            local_images.append(path)
            digest = sha256(path)
            require(digest not in image_hashes, f"README images have duplicate hash: {ref}")
            image_hashes.add(digest)
    final_gif = ROOT / "docs" / "assets" / "showcase-final" / "main-open-task-closed-loop.gif"
    require(final_gif.is_file(), "final showcase GIF is missing")
    require(final_gif.stat().st_size <= 3 * 1024 * 1024, "final showcase GIF exceeds 3 MB")

    ignored = subprocess.run(["git", "check-ignore", "-q", "mall-ai-service/tmp/"], cwd=ROOT)
    require(ignored.returncode == 0, "mall-ai-service/tmp/ is not ignored")
    tracked = git("ls-files").splitlines()
    # Names such as ``.env.example`` and Java DTOs containing ``Password`` or
    # ``Session`` are intentional source/templates.  Reject only actual local
    # env files and private-key/credential artifacts.
    risky = [
        p for p in tracked
        if re.search(r"(^|/)\.env$|(^|/)\.env\.(?!example$)|(^|/)(id_rsa|credentials?|.*\.(pem|key|p12))$", p, re.I)
    ]
    require(not risky, f"sensitive-looking tracked paths found: {', '.join(risky)}")
    require(not any("mall-ai-service/tmp/" in p for p in tracked), "raw tmp reports are tracked")

    head = git("rev-parse", "HEAD")
    runtime = facts["runtimeCommit"]
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", runtime, head], cwd=ROOT)
    require(ancestor.returncode == 0, "runtimeCommit is not an ancestor of HEAD")
    post_runtime = git("diff", "--name-only", f"{runtime}..HEAD").splitlines()
    runtime_prefixes = ("mall-ai-service/app/", "mall2/", "mall-ai-web/src/", "evals/", "mall2/document/sql/migrations/")
    changed_runtime = [p for p in post_runtime if p.startswith(runtime_prefixes)]
    require(not changed_runtime, f"runtime files changed after evaluated commit: {', '.join(changed_runtime)}")

    # Current sections of evidence docs must match; old sections remain allowed only
    # below the explicit historical marker.
    current_docs = [
        ROOT / "docs" / "evidence" / "release-gate-summary.md",
        ROOT / "docs" / "evidence" / "resume-fact-pack.md",
        ROOT / "docs" / "final-handoff" / "00-final-status.md",
        ROOT / "docs" / "final-handoff" / "03-test-evaluation-evidence.md",
    ]
    for path in current_docs:
        section = current_section(path)
        require("72/72" in section and "36/36" in section and "122/122" in section, f"current claims incomplete in {path}")
        require("14/14" not in section and "holdout" not in section.lower(), f"stale wording remains in current document {path}")
        require("365" in section, f"FastAPI 365 is missing in current document {path}")
    require("supplemental" in current_section(ROOT / "docs" / "evidence" / "release-gate-summary.md").lower(), "release summary does not label supplemental evaluation")
    require(ci["status"] in {"pending_remote_final_sha", "passed"}, "CI status must be explicit")

    print(
        "public_release_validation PASSED "
        f"head={head[:12]} runtime={runtime[:12]} "
        f"main={main_eval['passed']}/{main_eval['executed']} supplemental={supplemental['passed']}/{supplemental['executed']} "
        f"field={field['total']} images={len(local_images)} ci={ci['status']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
