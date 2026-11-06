from decimal import Decimal

import pytest
from django.db import IntegrityError

from apps.accounts.models import Role
from apps.workforce.models import Employee

pytestmark = pytest.mark.django_db


def test_employee_can_exist_without_a_user_account(make_employee):
    employee = make_employee(role=None)

    assert employee.user is None


def test_a_user_links_to_at_most_one_employee(make_employee, make_user):
    user = make_user(role=Role.LEADHAND)
    make_employee(user=user)

    with pytest.raises(IntegrityError):
        make_employee(user=user)


def test_employee_number_is_unique_but_optional(make_employee):
    make_employee(role=None, employee_number="")
    make_employee(role=None, employee_number="")  # blanks are stored as NULL
    make_employee(role=None, employee_number="E-100")

    assert Employee.objects.filter(employee_number__isnull=True).count() == 2
    with pytest.raises(IntegrityError):
        make_employee(role=None, employee_number="E-100")


def test_hourly_rate_cannot_be_negative(make_employee):
    with pytest.raises(IntegrityError):
        make_employee(role=None, hourly_rate=Decimal("-1"))


def test_hourly_rate_keeps_sub_cent_precision(make_employee):
    employee = make_employee(role=None, hourly_rate=Decimal("18.3333"))
    employee.refresh_from_db()

    assert employee.hourly_rate == Decimal("18.3333")
