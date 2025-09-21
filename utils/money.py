from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


def to_decimal(value: object) -> Decimal:
    """Convert arbitrary value to :class:`Decimal`."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def format_money(value: object) -> str:
    """Format monetary value without trailing zeros."""
    normalized = to_decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text
