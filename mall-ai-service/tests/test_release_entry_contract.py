"""Offline release-entry and ledger initialization contracts."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.llm_service import generate_text
from app.services.provider_guard import provider_access_context
from app.services.release_ledger import (
    ReleaseLedgerIntegrityError,
    read_release_events,
    release_ledger_context,
    reserve_provider_attempt,
    summarize_release_events,
)
from app.services.llm_observability import capture_llm_metrics
from scripts.release_entry_contract import (
    ReleaseEntryContractError,
    initialize_release_ledger,
)


class _FakeProvider(BaseHTTPRequestHandler):
    requests = 0

    def do_POST(self) -> None:  # noqa: N802
        type(self).requests += 1
        size = int(self.headers.get("content-length", "0"))
        self.rfile.read(size)
        payload = {
            "choices": [{"message": {"content": "synthetic"}}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
        }
        encoded = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        del format, args


def _entry(tmp_path: Path, *, container_path: str = "/app/release-ledger/ledger.jsonl") -> tuple[Path, Path, Path]:
    directory = tmp_path / "release-ledger"
    ledger = directory / "ledger.jsonl"
    lock = tmp_path / "release-lock.json"
    initialize_release_ledger(
        ledger_directory=directory,
        ledger_path=ledger,
        lock_path=lock,
        container_ledger_path=container_path,
    )
    return directory, ledger, lock


def test_formal_entry_creates_one_new_empty_ledger(tmp_path: Path) -> None:
    directory, ledger, _ = _entry(tmp_path)
    assert directory.is_dir()
    assert ledger.is_file()
    assert ledger.read_bytes() == b""


def test_existing_ledger_or_lock_is_rejected_without_truncation(tmp_path: Path) -> None:
    directory = tmp_path / "release-ledger"
    ledger = directory / "ledger.jsonl"
    lock = tmp_path / "release-lock.json"
    directory.mkdir()
    ledger.write_text("historical\n", encoding="utf-8")
    with pytest.raises(ReleaseEntryContractError, match="ledger_already_exists"):
        initialize_release_ledger(ledger_directory=directory, ledger_path=ledger, lock_path=lock, container_ledger_path="/app/release-ledger/ledger.jsonl")
    assert ledger.read_text(encoding="utf-8") == "historical\n"
    ledger.unlink()
    lock.write_text("{}", encoding="utf-8")
    with pytest.raises(ReleaseEntryContractError, match="release_lock_already_exists"):
        initialize_release_ledger(ledger_directory=directory, ledger_path=ledger, lock_path=lock, container_ledger_path="/app/release-ledger/ledger.jsonl")


def test_host_container_path_mismatch_fails_before_creation(tmp_path: Path) -> None:
    directory = tmp_path / "release-ledger"
    with pytest.raises(ReleaseEntryContractError, match="ledger_container_path_mismatch"):
        initialize_release_ledger(
            ledger_directory=directory,
            ledger_path=directory / "ledger.jsonl",
            lock_path=tmp_path / "lock.json",
            container_ledger_path="/wrong/ledger.jsonl",
        )
    assert not directory.exists()


def test_empty_entry_ledger_reserves_and_settles_first_fake_provider_attempt(tmp_path: Path) -> None:
    _, ledger, _ = _entry(tmp_path)
    _FakeProvider.requests = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeProvider)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        settings = SimpleNamespace(
            deepseek_api_key="fixture-only",
            deepseek_model="deepseek-flash",
            deepseek_base_url=f"http://127.0.0.1:{server.server_port}",
            deepseek_timeout_seconds=2.0,
        )
        with patch("app.services.llm_service.settings", settings), patch.dict(
            "os.environ",
            {
                "MALL_RELEASE_MAX_PROVIDER_HTTP_ATTEMPTS": "2",
                "MALL_RELEASE_MAX_TOTAL_TOKENS": "24000",
                "MALL_RELEASE_RESERVE_TOKENS": "12000",
                "MALL_RUNTIME_COMMIT": "a" * 40,
            },
            clear=False,
        ), release_ledger_context(batch_id="entry-rehearsal", path=ledger, source="entry-test"), provider_access_context(
            mode="mock", release_id="fixture-release", batch_id="entry-rehearsal", ledger_path=str(ledger), runtime_commit="a" * 40, authorized=True, allow_mock=True
        ), capture_llm_metrics(max_attempts=1, timeout_seconds=2.0):
            assert generate_text("fixture") == "synthetic"
        assert _FakeProvider.requests == 1
        events = read_release_events(ledger, batch_id="entry-rehearsal")
        summary = summarize_release_events(events)
        assert summary["providerHttpAttempts"] == 1
        assert summary["providerRequests"] == 1
        assert summary["providerSuccesses"] == 1
        assert summary["totalTokens"] == 5
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_missing_ledger_still_fails_closed_before_network(tmp_path: Path) -> None:
    ledger = tmp_path / "missing.jsonl"
    with patch.dict("os.environ", {"MALL_RELEASE_MAX_PROVIDER_HTTP_ATTEMPTS": "2", "MALL_RELEASE_BATCH_ID": "missing-ledger"}, clear=False), release_ledger_context(batch_id="missing-ledger", path=ledger):
        with pytest.raises(ReleaseLedgerIntegrityError):
            reserve_provider_attempt()
    assert not ledger.exists()
