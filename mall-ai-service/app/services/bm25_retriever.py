"""Local BM25 retrieval over the reviewed Markdown policy corpus.

This module is intentionally small and dependency-free.  The project corpus
is Chinese and compact, so a deterministic character-ngram tokenizer is more
auditable here than adding a remote tokenizer service or silently relying on a
general English analyzer.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import log
from pathlib import Path
from threading import Lock
from typing import Iterable
import re
import unicodedata

from app.schemas.rag import PolicyMetadataFilter, RetrievedChunk
from app.services.chunking_service import Chunk, chunk_directory
from app.services.policy_metadata import chunk_matches_filter


_CJK_RUN = re.compile(r"[\u3400-\u9fff]+")
_LATIN_OR_NUMBER = re.compile(r"[a-z0-9]+")
_cache_lock = Lock()
_index_cache: dict[tuple[str, tuple[tuple[str, int, int], ...]], "BM25PolicyIndex"] = {}


def tokenize_policy_text(text: str) -> list[str]:
    """Produce stable lexical terms for Chinese and ASCII policy text.

    A CJK character alone is often too broad, whereas an entire sentence is
    too strict for a paraphrase.  Unigrams plus overlapping bi/tri-grams give
    BM25 a deterministic exact-term signal while dense retrieval remains the
    semantic-paraphrase path.
    """
    normalized = unicodedata.normalize("NFKC", text).lower()
    tokens: list[str] = []

    for run in _CJK_RUN.findall(normalized):
        tokens.extend(run)
        for width in (2, 3):
            tokens.extend(
                run[index : index + width]
                for index in range(max(0, len(run) - width + 1))
            )

    tokens.extend(_LATIN_OR_NUMBER.findall(normalized))
    return tokens


@dataclass(frozen=True)
class BM25Hit:
    chunk: Chunk
    score: float
    rank: int


class BM25PolicyIndex:
    """A reusable in-process BM25 index for the approved Markdown chunks."""

    def __init__(self, chunks: Iterable[Chunk], *, k1: float = 1.5, b: float = 0.75):
        self.chunks = list(chunks)
        self.k1 = k1
        self.b = b
        self._term_frequencies = [Counter(tokenize_policy_text(chunk.text)) for chunk in self.chunks]
        self._document_frequencies: Counter[str] = Counter()
        for frequencies in self._term_frequencies:
            self._document_frequencies.update(frequencies.keys())
        self._document_lengths = [sum(frequencies.values()) for frequencies in self._term_frequencies]
        self._average_document_length = (
            sum(self._document_lengths) / len(self._document_lengths)
            if self._document_lengths
            else 0.0
        )

    def search(
        self,
        query: str,
        top_k: int,
        *,
        metadata_filter: PolicyMetadataFilter | dict | None = None,
    ) -> list[RetrievedChunk]:
        if top_k <= 0 or not self.chunks:
            return []
        query_terms = set(tokenize_policy_text(query))
        if not query_terms:
            return []

        eligible_indices = [
            index
            for index, chunk in enumerate(self.chunks)
            if chunk_matches_filter(chunk, metadata_filter)
        ]
        if not eligible_indices:
            return []
        scored: list[tuple[float, Chunk]] = []
        total_documents = len(eligible_indices)
        document_frequencies: Counter[str] = Counter()
        for index in eligible_indices:
            document_frequencies.update(self._term_frequencies[index].keys())
        for index in eligible_indices:
            chunk = self.chunks[index]
            score = 0.0
            frequencies = self._term_frequencies[index]
            document_length = self._document_lengths[index]
            for term in query_terms:
                frequency = frequencies.get(term, 0)
                if not frequency:
                    continue
                document_frequency = document_frequencies.get(term, 0)
                inverse_document_frequency = log(
                    1 + (total_documents - document_frequency + 0.5) / (document_frequency + 0.5)
                )
                denominator = frequency + self.k1 * (
                    1 - self.b + self.b * document_length / max(self._average_document_length, 1.0)
                )
                score += inverse_document_frequency * (frequency * (self.k1 + 1)) / denominator
            if score > 0:
                scored.append((score, chunk))

        scored.sort(key=lambda item: (-item[0], item[1].chunk_id))
        results: list[RetrievedChunk] = []
        for rank, (score, chunk) in enumerate(scored[:top_k], start=1):
            results.append(
                RetrievedChunk(
                    chunk_id=chunk.chunk_id,
                    document_name=chunk.document_title or chunk.source or "未知文档",
                    section_path=chunk.section_path or chunk.title or "未知章节",
                    text=chunk.text,
                    # Chroma cosine distance is not defined for BM25-only hits.
                    # Keep the legacy field compatible and use bm25_score/rank
                    # for Hybrid candidate admission instead.
                    distance=1.0,
                retrieval_method="bm25",
                bm25_rank=rank,
                bm25_score=round(score, 8),
                document_id=chunk.document_id or chunk.source or chunk.document_title or None,
                heading_path=">".join(chunk.heading_path) or chunk.section_path or None,
                source_order=chunk.source_order or None,
                policy_version=chunk.policy_version or None,
                effective_from=chunk.effective_from or None,
                category=chunk.category or None,
                language=chunk.language or None,
                document_type=chunk.document_type or None,
                content_hash=chunk.content_hash or None,
            )
        )
        return results


def search_bm25(
    query: str,
    top_k: int,
    *,
    knowledge_dir: Path | None = None,
    metadata_filter: PolicyMetadataFilter | dict | None = None,
) -> list[RetrievedChunk]:
    """Search the current reviewed corpus with a cache that follows file changes."""
    index = _get_index(knowledge_dir)
    return index.search(query, top_k, metadata_filter=metadata_filter)


def clear_bm25_cache() -> None:
    """Test/support hook; normal runtime invalidates when corpus files change."""
    with _cache_lock:
        _index_cache.clear()


def _get_index(knowledge_dir: Path | None) -> BM25PolicyIndex:
    directory = knowledge_dir or Path(__file__).resolve().parents[1] / "knowledge"
    signature = _directory_signature(directory)
    key = (str(directory.resolve()), signature)
    with _cache_lock:
        cached = _index_cache.get(key)
        if cached is not None:
            return cached
        # There is only one active directory in normal runtime, so removing an
        # older signature avoids retaining every policy revision in memory.
        stale_keys = [cache_key for cache_key in _index_cache if cache_key[0] == key[0]]
        for stale_key in stale_keys:
            _index_cache.pop(stale_key, None)
        index = BM25PolicyIndex(chunk_directory(directory))
        _index_cache[key] = index
        return index


def _directory_signature(directory: Path) -> tuple[tuple[str, int, int], ...]:
    return tuple(
        (path.name, path.stat().st_mtime_ns, path.stat().st_size)
        for path in sorted(directory.glob("*.md"))
    )
