"""Money helpers. Amounts are Decimal rupees in code and integer paise in storage."""

from decimal import ROUND_HALF_UP, Decimal

ZERO = Decimal("0")
HUNDRED = Decimal("100")
_PAISE = Decimal("0.01")


def rupees(value: Decimal | int | str) -> Decimal:
    """Round to whole paise."""
    return Decimal(value).quantize(_PAISE, rounding=ROUND_HALF_UP)


def to_paise(amount: Decimal | int | str) -> int:
    return int((Decimal(amount) * HUNDRED).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def from_paise(paise: int) -> Decimal:
    return (Decimal(paise) / HUNDRED).quantize(_PAISE)


def percent(part: Decimal, whole: Decimal) -> Decimal:
    """part as a percentage of whole, 0 to 100 with two decimals. Zero when whole is zero."""
    if whole == 0:
        return ZERO.quantize(_PAISE)
    return (Decimal(part) * HUNDRED / Decimal(whole)).quantize(_PAISE, rounding=ROUND_HALF_UP)
