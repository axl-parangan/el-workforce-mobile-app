"""Monetary rounding policy (ADR 005).

Calculate at full Decimal precision and round only the final payable amount,
to cents, using ROUND_HALF_UP.
"""

from decimal import ROUND_HALF_UP, Decimal

MONEY_QUANTUM = Decimal("0.01")


def round_money(amount: Decimal) -> Decimal:
    if not isinstance(amount, Decimal):
        # A float has already lost precision; refuse it rather than hide the bug.
        raise TypeError(f"Expected Decimal, got {type(amount).__name__}")
    return amount.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
