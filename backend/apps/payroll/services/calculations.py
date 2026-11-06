"""Pay calculations, one function per compensation type (ADR 005).

Functions take already-approved inputs and return a Decimal amount. They do
not read the database or decide what is approved.

TODO: daily and fixed/task calculations. Pending business rules: what makes
a qualifying day, how fixed tasks are approved, breaks and overtime
(see docs/development/open-questions.md).
"""

from decimal import Decimal

from .money import round_money


def calculate_hourly_pay(*, approved_hours: Decimal, hourly_rate: Decimal) -> Decimal:
    """Approved payable hours x hourly rate, rounded once at the end."""
    for name, value in (("approved_hours", approved_hours), ("hourly_rate", hourly_rate)):
        if not isinstance(value, Decimal):
            raise TypeError(f"{name} must be a Decimal, got {type(value).__name__}")
        if value < 0:
            raise ValueError(f"{name} must not be negative")
    return round_money(approved_hours * hourly_rate)
