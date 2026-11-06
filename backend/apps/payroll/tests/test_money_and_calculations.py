from decimal import Decimal

import pytest

from apps.payroll.services.calculations import calculate_hourly_pay
from apps.payroll.services.money import round_money


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        ("2.345", "2.35"),  # half-up (banker's rounding would give 2.34)
        ("2.355", "2.36"),
        ("2.344999", "2.34"),
        ("10", "10.00"),
        ("-2.345", "-2.35"),  # half away from zero for adjustments
    ],
)
def test_round_money_uses_half_up_to_cents(amount, expected):
    assert round_money(Decimal(amount)) == Decimal(expected)


def test_round_money_rejects_floats():
    with pytest.raises(TypeError):
        round_money(2.345)


def test_hourly_pay_rounds_only_the_final_amount():
    # 7.75 h x 18.333 = 142.08075 -> 142.08. Rounding the rate first (18.33)
    # would give 142.0575 -> 142.06.
    assert calculate_hourly_pay(
        approved_hours=Decimal("7.75"), hourly_rate=Decimal("18.333")
    ) == Decimal("142.08")


def test_hourly_pay_half_up_on_final_amount():
    # 0.5 h x 0.01 = 0.005 -> 0.01
    assert calculate_hourly_pay(
        approved_hours=Decimal("0.5"), hourly_rate=Decimal("0.01")
    ) == Decimal("0.01")


def test_hourly_pay_zero_hours():
    assert calculate_hourly_pay(
        approved_hours=Decimal("0"), hourly_rate=Decimal("25.00")
    ) == Decimal("0.00")


@pytest.mark.parametrize(
    ("hours", "rate", "error"),
    [
        (7.5, Decimal("20"), TypeError),
        (Decimal("7.5"), 20, TypeError),
        (Decimal("-1"), Decimal("20"), ValueError),
        (Decimal("1"), Decimal("-20"), ValueError),
    ],
)
def test_hourly_pay_rejects_invalid_inputs(hours, rate, error):
    with pytest.raises(error):
        calculate_hourly_pay(approved_hours=hours, hourly_rate=rate)
