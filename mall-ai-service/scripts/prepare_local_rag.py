"""Prepare local RAG artifacts explicitly, outside the customer request path.

The public source repository deliberately excludes model weights and the
generated Chroma index.  This script downloads the reviewed local embedding
model on demand, copies only the runtime files into the stable project path,
and builds the policy index from committed policy Markdown.  It never needs a
DeepSeek key and never processes customer data.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
# When this file is invoked as `python scripts/prepare_local_rag.py`, Python
# starts with `scripts/` as sys.path[0]. Add the service root explicitly so the
# same command works from a clean clone as well as from the test runner.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
EMBEDDING_MODEL_NAME = "BAAI/bge-small-zh-v1.5"
EMBEDDING_TARGET = PROJECT_ROOT / "models" / "embedding" / "bge-small-zh-v1.5"
EMBEDDING_CACHE = PROJECT_ROOT / "models" / "embedding"
REQUIRED_EMBEDDING_FILES = (
    "model_optimized.onnx",
    "config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
)


def embedding_model_ready(target: Path = EMBEDDING_TARGET) -> bool:
    return all((target / name).is_file() for name in REQUIRED_EMBEDDING_FILES)


def copy_runtime_model_files(source: Path, target: Path = EMBEDDING_TARGET) -> None:
    """Copy the allow-listed runtime files from FastEmbed's cache only."""

    target.mkdir(parents=True, exist_ok=True)
    missing = [name for name in REQUIRED_EMBEDDING_FILES if not (source / name).is_file()]
    if missing:
        raise RuntimeError("Downloaded embedding model is incomplete: " + ", ".join(missing))
    for name in REQUIRED_EMBEDDING_FILES:
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, destination)


def download_embedding_model(target: Path = EMBEDDING_TARGET) -> None:
    if embedding_model_ready(target):
        print("Local embedding model is already ready.")
        return

    try:
        from fastembed import TextEmbedding

        description = TextEmbedding._get_model_description(EMBEDDING_MODEL_NAME)
        downloaded = TextEmbedding.download_model(description, cache_dir=str(EMBEDDING_CACHE))
    except Exception as exc:  # pragma: no cover - network/provider messages vary
        raise RuntimeError(
            "Could not download the reviewed local embedding model. "
            "Check normal network access and retry the explicit bootstrap command."
        ) from exc

    copy_runtime_model_files(Path(downloaded), target)
    print("Local embedding model is ready.")


def policy_index_ready() -> bool:
    try:
        from app.services import vector_store

        collection = vector_store._client.get_collection(name=vector_store.COLLECTION_NAME)
        vector_store._assert_collection_compatible(collection)
        return collection.count() > 0
    except Exception:
        return False


def build_policy_index() -> int:
    from app.services.vector_store import ingest_knowledge_base

    count = ingest_knowledge_base()
    if count <= 0:
        raise RuntimeError("Committed policy knowledge did not produce any RAG chunks.")
    print(f"Local policy index is ready: {count} chunks.")
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Do not access the network or rebuild the index.",
    )
    args = parser.parse_args(argv)

    if args.check_only:
        model_ok = embedding_model_ready()
        index_ok = policy_index_ready() if model_ok else False
        if model_ok and index_ok:
            print("Local RAG artifacts are ready.")
            return 0
        if not model_ok:
            print("Local embedding model is missing or incomplete.")
        if not index_ok:
            print("Local policy index is missing, empty, or incompatible.")
        return 2

    try:
        download_embedding_model()
        build_policy_index()
    except RuntimeError as exc:
        print(f"Local RAG bootstrap failed: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
