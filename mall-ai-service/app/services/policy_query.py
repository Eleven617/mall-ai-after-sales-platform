"""Safe, minimal query projection for policy retrieval components.

The policy retriever and local reranker do not need a browser token, order
number, contact detail, or the rest of a conversation.  This module creates a
bounded representation of the policy question before it leaves the RAG
boundary.  It is deliberately deterministic: Build 20 does not add a model
query-rewrite call to every customer request.
"""

from __future__ import annotations

import re
import unicodedata


MAX_POLICY_QUERY_CHARS = 480

_ORDER_LIKE_NUMBER = re.compile(r"(?<!\d)\d{10,24}(?!\d)")
_MAINLAND_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_JWT_LIKE_TOKEN = re.compile(
    r"\b[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
)
_BEARER_PREFIX = re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]+")
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WHITESPACE = re.compile(r"\s+")


def project_policy_query(value: str) -> str:
    """Return the bounded text allowed into local policy retrieval.

    This is not a semantic classifier and does not decide whether a customer
    is eligible for an after-sales operation.  It only removes identifier-like
    content that the local retrieval/rerank stages never need.
    """
    if not isinstance(value, str):
        return ""

    query = unicodedata.normalize("NFKC", value)
    query = _CONTROL_CHARACTERS.sub(" ", query)
    query = _JWT_LIKE_TOKEN.sub("[已移除令牌]", query)
    query = _BEARER_PREFIX.sub("[已移除令牌]", query)
    query = _EMAIL.sub("[已移除邮箱]", query)
    query = _MAINLAND_PHONE.sub("[已移除手机号]", query)
    query = _ORDER_LIKE_NUMBER.sub("[已移除订单号]", query)
    query = _WHITESPACE.sub(" ", query).strip()
    return query[:MAX_POLICY_QUERY_CHARS]
