"""Company-timezone helpers (ADR 008).

Instants are stored in UTC. Work dates for attendance and payroll are derived
by converting to the company's configured timezone, never the device's.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.conf import settings


def company_timezone() -> ZoneInfo:
    return ZoneInfo(settings.COMPANY_TIME_ZONE)


def to_company_time(instant: datetime) -> datetime:
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("Expected a timezone-aware datetime.")
    return instant.astimezone(company_timezone())


def work_date_for(instant: datetime) -> date:
    """The calendar date, in the company timezone, on which ``instant`` falls."""
    return to_company_time(instant).date()
