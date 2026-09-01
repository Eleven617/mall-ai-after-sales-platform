"""Reviewed customer-facing templates for the bounded ordinary-chat route.

The LLM still makes the semantic choice through the internal ``chat_scope``
enum produced by intent recognition. This module deliberately does not make a
second free-form LLM call, so a fresh conversation cannot escape into a generic
assistant identity or unrelated capabilities.
"""

from app.schemas.intent import ChatScope


_SCOPE_REPLIES: dict[ChatScope, str] = {
    "greeting": "您好，我可以帮您查询订单和物流、了解售后政策，或协助发起退换货申请。",
    "capability": "我可以协助查询订单、物流和库存，解答退换货、运费等售后政策，并引导您发起售后申请。",
    "out_of_scope": "我主要协助处理商城订单、物流、退换货和售后政策问题。您也可以告诉我订单号，我会继续为您查询。",
}


def reply_for_chat_scope(scope: ChatScope | None) -> str:
    """Return a safe mall-domain answer without exposing the internal enum."""
    return _SCOPE_REPLIES.get(scope or "out_of_scope", _SCOPE_REPLIES["out_of_scope"])
