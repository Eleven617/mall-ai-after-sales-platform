"""Conservative extraction of user-visible business identifiers.

These helpers intentionally prefer clarification over guessing.  They are used
by both the generic order-query continuation and the after-sales workflow so
that a phone number is never silently treated as an order number.
"""
from dataclasses import dataclass
import re


ORDER_LABEL_PATTERN = re.compile(
    r"(?:订单号|订单编号|订单|单号)\s*(?:为|是)?\s*[:：#]?\s*(\d{6,})"
)
LONG_NUMBER_PATTERN = re.compile(r"(?<!\d)(\d{6,})(?!\d)")
MOBILE_PHONE_PATTERN = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")
SKU_ID_PATTERN = re.compile(r"\bSKU[0-9A-Za-z_-]+\b", re.IGNORECASE)


@dataclass(frozen=True)
class IdentifierResolution:
    value: str | None = None
    ambiguous: bool = False
    candidates: tuple[str, ...] = ()


def extract_order_sn(message: str) -> IdentifierResolution:
    """Return one safe order-number candidate or request clarification.

    An explicit order-number label wins over unrelated numeric text.  Without
    that label, a mobile phone number is ignored and multiple long numbers are
    treated as ambiguous instead of selecting the last one.
    """
    labeled = _unique(ORDER_LABEL_PATTERN.findall(message))
    if len(labeled) == 1:
        return IdentifierResolution(value=labeled[0], candidates=tuple(labeled))
    if len(labeled) > 1:
        return IdentifierResolution(ambiguous=True, candidates=tuple(labeled))

    phone_numbers = set(MOBILE_PHONE_PATTERN.findall(message))
    candidates = [
        value for value in _unique(LONG_NUMBER_PATTERN.findall(message))
        if value not in phone_numbers
    ]
    if len(candidates) == 1:
        return IdentifierResolution(value=candidates[0], candidates=tuple(candidates))
    if len(candidates) > 1:
        return IdentifierResolution(ambiguous=True, candidates=tuple(candidates))
    return IdentifierResolution()


def extract_sku_id(message: str) -> IdentifierResolution:
    candidates = _unique(match.upper() for match in SKU_ID_PATTERN.findall(message))
    if len(candidates) == 1:
        return IdentifierResolution(value=candidates[0], candidates=tuple(candidates))
    if len(candidates) > 1:
        return IdentifierResolution(ambiguous=True, candidates=tuple(candidates))
    return IdentifierResolution()


def _unique(values: object) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:  # type: ignore[union-attr]
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
