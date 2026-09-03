"""Write a safe, reproducible v3.0 baseline manifest.

The manifest records versions and command names only.  It deliberately does
not inspect environment files or include credentials, customer data, model
prompts, raw traces or generated indexes.  Run it after the commit that is
being verified; ``rootCommit`` therefore identifies the tested source tree.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "mall-ai-service"
MANIFEST = ROOT / "evals" / "v3" / "release-manifest.json"
DEFAULT_OUTPUT = ROOT / "docs" / "evidence" / "v3.0-baseline-manifest.json"


def _resolve_command(name: str) -> str | None:
    """Resolve commands portably without executing through a shell.

    GitHub's Linux runner exposes executables directly, while the local
    Windows toolchain commonly exposes Maven/npm as ``.cmd`` shims.  Looking
    up the concrete executable keeps the manifest honest on both platforms
    and avoids shell interpolation of any environment content.
    """
    candidates = [name]
    if sys.platform.startswith("win") and not name.lower().endswith((".cmd", ".exe")):
        candidates.extend((f"{name}.cmd", f"{name}.exe"))
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def _command(*args: str, cwd: Path = ROOT) -> str:
    executable = _resolve_command(args[0])
    if executable is None:
        return "unavailable"
    try:
        completed = subprocess.run(
            [executable, *args[1:]],
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return "unavailable"
    if completed.returncode != 0:
        return "unavailable"
    value = (completed.stdout or completed.stderr).strip().splitlines()
    # An empty successful result is meaningful (for example, a clean
    # ``git status --porcelain``) and must not be conflated with an
    # unavailable command.
    return value[0][:160] if value else ""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_status_clean(output_path: Path = DEFAULT_OUTPUT) -> bool | str:
    """Report source-tree cleanliness without counting this generated file.

    The manifest is intentionally written after the tested commit, so the
    output itself is expected to become modified while it is being produced.
    Excluding only that exact repository-relative path keeps the recorded
    value useful: ``True`` means all other tracked/untracked source content
    was clean at generation time.
    """
    try:
        relative_output = output_path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        relative_output = ""
    args = ["git", "status", "--porcelain"]
    if relative_output:
        args.extend(["--", ".", f":!{relative_output}"])
    value = _command(*args)
    if value == "unavailable":
        return "unavailable"
    return value == ""


def build_manifest(output_path: Path = DEFAULT_OUTPUT) -> dict[str, object]:
    root_commit = _command("git", "rev-parse", "HEAD")
    nested_git = ROOT / "mall2" / ".git"
    java_commit = (
        _command("git", "-C", "mall2", "rev-parse", "HEAD")
        if nested_git.exists()
        else "vendored-source-no-nested-git"
    )
    if java_commit == "unavailable":
        java_commit = "vendored-source-no-nested-git"
    return {
        "schemaVersion": "v3.0-baseline.v1",
        "generatedAtUtc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "rootCommit": root_commit,
        "gitStatusClean": _git_status_clean(output_path),
        "javaSource": {
            "strategy": "vendored-source-with-upstream-base-and-local-patch-boundary",
            "nestedWorktreeCommit": java_commit,
            "upstream": "macrozheng/mall",
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform()[:160],
            "node": _command("node", "--version"),
            "npm": _command("npm", "--version"),
            "java": _command("java", "-version"),
            "maven": _command("mvn", "-version"),
            "docker": _command("docker", "--version"),
        },
        "fixtures": {
            "releaseManifest": "evals/v3/release-manifest.json",
            "releaseManifestSha256": _sha256(MANIFEST) if MANIFEST.exists() else "missing",
        },
        "verificationCommands": [
            "python -m compileall -q app",
            "python -m pytest --collect-only -q",
            "python -m pytest -q",
            "python scripts/run_v3_release_preflight.py --json",
            "npm ci && npm run build",
            "mvn -pl mall-portal -am -DskipTests=false test",
            "mvn -pl mall-admin -am -DskipTests=false test",
            "docker compose --env-file .env.example config --quiet",
        ],
        "scope": {
            "data": "synthetic/local only",
            "liveModel": "not run by default CI",
            "productionClaims": False,
            "externalFulfillment": "not connected",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = build_manifest(args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
