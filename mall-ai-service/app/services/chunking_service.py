"""Deterministic, policy-aware Markdown chunking.

The reviewed corpus is intentionally small.  A heading is therefore the
primary rule boundary; long sections are packed by paragraph/sentence only
when necessary.  We do not force a fixed-size split through a condition,
exception, bullet list, or Markdown table.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


CHUNK_CONTRACT_VERSION = "chunk-v2"
TARGET_CHUNK_CHARS = 800
MIN_CHUNK_CHARS = 40
MAX_CHUNK_CHARS = 1200
CHUNK_OVERLAP_CHARS = 80


@dataclass
class Chunk:
    """知识库中的一个文本片段"""

    text: str
    title: str = ""  # 所属的最末级标题，比如"七天无理由退货"
    source: str = ""  # 来源文件名
    document_title: str = ""
    section_path: str = ""
    chunk_id: str = ""
    # v2 contract fields.  Defaults keep hand-written unit-test fixtures and
    # the Build 20 retrieval interfaces source-compatible.
    document_id: str = ""
    heading_path: tuple[str, ...] = ()
    source_order: int = 0
    policy_version: str = ""
    effective_from: str = ""
    category: str = ""
    language: str = ""
    document_type: str = ""
    content_hash: str = ""
    effective_from_ts: int = 0


_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_VERSION_PATTERN = re.compile(r"\bV(\d+(?:\.\d+)*)\b", re.IGNORECASE)
_DATE_PATTERN = re.compile(r"(?:更新于|生效于|effective(?:[_ -]?from)?)\s*[:：]?\s*(\d{4}-\d{2}-\d{2})", re.IGNORECASE)
_CATEGORY_PATTERN = re.compile(r"^\s*(?:类别|分类|category)\s*[:：:]\s*([^\n]+)", re.IGNORECASE | re.MULTILINE)
_LANGUAGE_PATTERN = re.compile(r"^\s*(?:语言|language)\s*[:：:]\s*([^\n]+)", re.IGNORECASE | re.MULTILINE)
_DOCUMENT_TYPE_PATTERN = re.compile(r"^\s*(?:文档类型|document[_ -]?type)\s*[:：:]\s*([^\n]+)", re.IGNORECASE | re.MULTILINE)
_SENTENCE_BOUNDARY = re.compile(r"(?<=[。！？；.!?;])\s*")


def extract_document_metadata(content: str, file_path: Path) -> dict[str, str | int]:
    """Extract explicit document metadata without asking an LLM.

    Existing demo files use a human-readable blockquote (for example
    ``业务规则 V1.1，更新于 2026-08-04``), so the parser supports that form
    and optional ``类别``/``文档类型`` lines.  Defaults are conservative and
    are recorded in the index rather than inferred from a customer query.
    """

    first_heading = next(
        (
            match.group(2).strip()
            for line in content.splitlines()
            if (match := _HEADING_PATTERN.match(line)) is not None and len(match.group(1)) == 1
        ),
        file_path.stem,
    )
    version_match = _VERSION_PATTERN.search(content)
    date_match = _DATE_PATTERN.search(content)
    category_match = _CATEGORY_PATTERN.search(content)
    language_match = _LANGUAGE_PATTERN.search(content)
    document_type_match = _DOCUMENT_TYPE_PATTERN.search(content)
    effective_from = date_match.group(1) if date_match else ""
    return {
        "document_id": file_path.stem,
        "document_title": first_heading,
        "policy_version": f"V{version_match.group(1)}" if version_match else "unknown",
        "effective_from": effective_from,
        "effective_from_ts": _date_to_timestamp(effective_from),
        "category": (category_match.group(1).strip() if category_match else "after_sales"),
        "language": (language_match.group(1).strip() if language_match else _detect_language(content)),
        "document_type": (document_type_match.group(1).strip() if document_type_match else "policy"),
    }


def chunk_markdown_file(file_path: Path) -> list[Chunk]:
    """Split Markdown by headings while preserving a stable evidence path.

    ``source_order`` is one-based within a document.  The current corpus keeps
    one chunk per policy heading because every section is below the configured
    maximum; long future sections are split only at paragraph/sentence
    boundaries with a small overlap.
    """
    return chunk_markdown_text(
        file_path.read_text(encoding="utf-8"),
        source=file_path.name,
    )


def chunk_markdown_text(content: str, *, source: str = "memory.md") -> list[Chunk]:
    """Chunk a versioned Markdown string without needing a runtime file.

    The committed policy loader uses :func:`chunk_markdown_file`; this helper
    keeps synthetic structure/metadata evaluations file-system independent.
    ``source`` is a stable logical filename and becomes the document ID.
    """

    file_path = Path(source)
    chunks: list[Chunk] = []

    metadata = extract_document_metadata(content, file_path)
    document_title = str(metadata["document_title"])
    current_path: list[str] = []
    current_body: list[str] = []

    def flush() -> None:
        body = "\n".join(current_body).strip()
        if not body or not current_path:
            return
        section_path = " > ".join([document_title, *current_path])
        body_parts = _split_rule_body(body)
        for part_index, part in enumerate(body_parts):
            text = f"{section_path}\n{part}".strip()
            # Keep IDs stable for the existing unsplit corpus.  A split part
            # gets its ordinal so two identical sentences cannot collide.
            id_suffix = "" if len(body_parts) == 1 else f"\0{part_index}"
            chunk_id = hashlib.sha256(
                f"{file_path.name}\0{section_path}{id_suffix}\0{part}".encode("utf-8")
            ).hexdigest()[:20]
            content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            chunks.append(
                Chunk(
                    text=text,
                    title=current_path[-1],
                    source=file_path.name,
                    document_title=document_title,
                    section_path=section_path,
                    chunk_id=chunk_id,
                    document_id=str(metadata["document_id"]),
                    heading_path=tuple(current_path),
                    source_order=len(chunks) + 1,
                    policy_version=str(metadata["policy_version"]),
                    effective_from=str(metadata["effective_from"]),
                    category=str(metadata["category"]),
                    language=str(metadata["language"]),
                    document_type=str(metadata["document_type"]),
                    content_hash=content_hash,
                    effective_from_ts=int(metadata["effective_from_ts"]),
                )
            )

    for line in content.splitlines():
        heading = _HEADING_PATTERN.match(line)
        if heading is None:
            current_body.append(line)
            continue

        level = len(heading.group(1))
        title = heading.group(2).strip()
        if level == 1:
            flush()
            current_body = []
            document_title = title
            current_path = []
            continue

        if level == 2:
            # A level-two heading is a policy rule boundary.  Its nested
            # headings (conditions, exceptions, procedures, tables) stay in
            # the same semantic rule block instead of becoming disconnected
            # micro-chunks.
            flush()
            current_body = []
            current_path = [title]
            continue

        # Preserve lower-level labels inside the current top-level policy
        # rule.  They give the answer model the condition/exception context
        # without mechanically separating it from the rule conclusion.
        if current_path:
            current_body.append(line)

    flush()

    return chunks


def chunk_directory(knowledge_dir: Path) -> list[Chunk]:
    """读取目录下所有 .md 文件，全部切分成 chunk"""
    all_chunks: list[Chunk] = []
    for md_file in sorted(knowledge_dir.glob("*.md")):
        all_chunks.extend(chunk_markdown_file(md_file))
    return all_chunks


def _split_rule_body(body: str) -> list[str]:
    """Pack long rule text without cutting tables or rule boundaries."""

    if len(body) <= MAX_CHUNK_CHARS:
        return [body]

    blocks = [block.strip() for block in re.split(r"\n\s*\n", body) if block.strip()]
    units: list[str] = []
    for block in blocks:
        if _is_table_block(block) or len(block) <= MAX_CHUNK_CHARS:
            units.append(block)
            continue
        # A paragraph that is too long is split only at sentence punctuation.
        # An unbroken/table-like unit remains oversized rather than being cut
        # in the middle of a condition or exception.
        units.extend(
            sentence.strip()
            for sentence in _SENTENCE_BOUNDARY.split(block)
            if sentence.strip()
        )

    parts: list[str] = []
    current = ""
    for unit in units:
        candidate = f"{current}\n\n{unit}" if current else unit
        if current and len(candidate) > MAX_CHUNK_CHARS:
            parts.append(current)
            overlap = _overlap_tail(current)
            current = f"{overlap}\n\n{unit}" if overlap else unit
        else:
            current = candidate
    if current:
        parts.append(current)
    if len(parts) > 1 and len(parts[-1]) < MIN_CHUNK_CHARS:
        merged_tail = f"{parts[-2]}\n\n{parts[-1]}"
        if len(merged_tail) <= MAX_CHUNK_CHARS:
            parts[-2:] = [merged_tail]
    return parts or [body]


def _is_table_block(value: str) -> bool:
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    return bool(lines) and sum(line.startswith("|") for line in lines) >= max(2, len(lines) // 2)


def _overlap_tail(value: str) -> str:
    tail = value[-CHUNK_OVERLAP_CHARS:]
    # Avoid starting the next chunk with half a Markdown bullet where possible.
    newline = tail.find("\n")
    return tail[newline + 1 :].strip() if newline >= 0 else tail.strip()


def _detect_language(content: str) -> str:
    cjk = len(re.findall(r"[\u3400-\u9fff]", content))
    latin = len(re.findall(r"[A-Za-z]", content))
    return "zh-CN" if cjk >= latin else "en"


def _date_to_timestamp(value: str) -> int:
    if not value:
        return 0
    try:
        return int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp())
    except ValueError:
        return 0
