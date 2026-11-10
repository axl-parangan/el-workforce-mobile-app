"""Employee read queries for staff pickers (assignment, LeadHand designation)."""

from __future__ import annotations

from django.db.models import Q, QuerySet

from apps.workforce.models import Employee

# Filter value for employees without an app account.
NO_ACCOUNT = "none"


def employee_list(
    *,
    search: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
) -> QuerySet[Employee]:
    """Employees ordered by name. ``role`` is an account role, or ``"none"``."""
    queryset = Employee.objects.select_related("user")
    if search:
        queryset = queryset.filter(Q(name__icontains=search) | Q(employee_number__icontains=search))
    if role == NO_ACCOUNT:
        queryset = queryset.filter(user__isnull=True)
    elif role:
        queryset = queryset.filter(user__role=role)
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)
    return queryset.order_by("name", "pk")
