"""Deterministic cent rounding for published PHP prices."""
from decimal import Decimal, ROUND_HALF_EVEN


_CENT = Decimal("0.01")


def round_price(value):
    """Round a price to cents without binary floating-point tie drift."""
    return float(Decimal(str(value)).quantize(_CENT, rounding=ROUND_HALF_EVEN))


def mean_price(values):
    """Average prices and round the published result to cents."""
    values = [Decimal(str(value)) for value in values]
    if not values:
        raise ValueError("Cannot average an empty price period")
    return float((sum(values, Decimal("0")) / len(values)).quantize(
        _CENT, rounding=ROUND_HALF_EVEN))
