"""Initialize one new release ledger without weakening ledger fail-closed checks.

The formal release entry owns creation of a *new* empty JSONL file.  Runtime
reservation code must continue to reject a missing or malformed file so a bad
mount cannot be hidden by implicit creation inside the service.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


class ReleaseEntryContractError(RuntimeError):
    """A release cannot safely own the requested ledger/lock paths."""


CONTAINER_LEDGER_PATH = "/app/release-ledger/ledger.jsonl"


def initialize_release_ledger(
    *,
    ledger_directory: str | Path,
    ledger_path: str | Path,
    lock_path: str | Path,
    container_ledger_path: str,
) -> Path:
    """Atomically create a new empty ledger and reject reuse.

    This function never removes or truncates an existing file.  It also
    requires the container path used by Compose to be the reviewed fixed path;
    the host directory is mounted to that path by the release entry.
    """

    directory = Path(ledger_directory).expanduser().resolve()
    path = Path(ledger_path).expanduser().resolve()
    lock = Path(lock_path).expanduser().resolve()
    if container_ledger_path != CONTAINER_LEDGER_PATH:
        raise ReleaseEntryContractError("ledger_container_path_mismatch")
    if path != directory / "ledger.jsonl":
        raise ReleaseEntryContractError("ledger_host_path_mismatch")
    if path.exists():
        raise ReleaseEntryContractError("ledger_already_exists")
    if lock.exists():
        raise ReleaseEntryContractError("release_lock_already_exists")
    if directory.exists() and not directory.is_dir():
        raise ReleaseEntryContractError("ledger_directory_not_directory")
    if directory.exists() and any(directory.iterdir()):
        raise ReleaseEntryContractError("ledger_directory_not_empty")
    directory.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(descriptor)
    except FileExistsError as exc:
        raise ReleaseEntryContractError("ledger_already_exists") from exc
    except OSError as exc:
        raise ReleaseEntryContractError("ledger_create_failed") from exc
    if path.stat().st_size != 0:
        raise ReleaseEntryContractError("ledger_not_empty_after_create")
    try:
        # Opening read/write verifies the host bind source is writable without
        # changing the empty ledger or exposing any ledger content.
        descriptor = os.open(str(path), os.O_RDWR)
        os.close(descriptor)
    except OSError as exc:
        raise ReleaseEntryContractError("ledger_host_not_readwrite") from exc
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger-directory", required=True)
    parser.add_argument("--ledger-path", required=True)
    parser.add_argument("--lock-path", required=True)
    parser.add_argument("--container-ledger-path", default=CONTAINER_LEDGER_PATH)
    args = parser.parse_args()
    try:
        path = initialize_release_ledger(
            ledger_directory=args.ledger_directory,
            ledger_path=args.ledger_path,
            lock_path=args.lock_path,
            container_ledger_path=args.container_ledger_path,
        )
    except ReleaseEntryContractError as exc:
        print(json.dumps({"status": "blocked", "failureCode": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": "passed", "ledgerCreated": True, "ledgerEmpty": path.stat().st_size == 0}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
