"""Explicitly download the reviewed local Build 20 Cross-Encoder model.

This setup command is deliberately separate from the customer request path.
The RAG service refuses to auto-download a missing model, avoiding surprise
network/disk use during a demo or production-like run.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET = PROJECT_ROOT / "models" / "reranker" / "bge-reranker-base"
REQUIRED_FILES = ("onnx/model.onnx", "config.json", "tokenizer.json")
MIN_FREE_BYTES = 2 * 1024 * 1024 * 1024


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument(
        "--check-only", action="store_true", help="Do not access the network."
    )
    args = parser.parse_args()
    target = args.target.resolve()
    if _is_ready(target):
        print(f"Reranker model is ready: {target}")
        return 0
    if args.check_only:
        print(f"Reranker model is incomplete: {target}")
        return 2

    free_bytes = shutil.disk_usage(target.parent if target.parent.exists() else PROJECT_ROOT).free
    if free_bytes < MIN_FREE_BYTES:
        print("Insufficient free disk space for the local reranker model.")
        return 2
    target.mkdir(parents=True, exist_ok=True)
    try:
        from huggingface_hub import snapshot_download

        snapshot_download(
            repo_id="BAAI/bge-reranker-base",
            allow_patterns=[
                "config.json",
                "onnx/model.onnx",
                "sentencepiece.bpe.model",
                "special_tokens_map.json",
                "tokenizer.json",
                "tokenizer_config.json",
            ],
            local_dir=str(target),
        )
    except Exception as exc:
        print("Reranker model download failed; check normal network access and retry this explicit setup command.")
        return 2
    if not _is_ready(target):
        print("Reranker model download completed but required files are incomplete.")
        return 2
    print(f"Reranker model is ready: {target}")
    return 0


def _is_ready(target: Path) -> bool:
    return all((target / relative).is_file() for relative in REQUIRED_FILES)


if __name__ == "__main__":
    raise SystemExit(main())
