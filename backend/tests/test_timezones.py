from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from common.timezones import company_timezone, to_company_time, work_date_for


def test_company_timezone_defaults_to_toronto():
    assert company_timezone().key == "America/Toronto"


def test_late_evening_shift_belongs_to_the_toronto_date_not_the_utc_date():
    # 22:30 in Toronto on Nov 5 (EST, UTC-5) is already Nov 6 in UTC.
    instant = datetime(2026, 11, 6, 3, 30, tzinfo=UTC)

    assert work_date_for(instant) == date(2026, 11, 5)


def test_daylight_saving_offset_is_applied():
    # 23:30 EDT (UTC-4) on Jun 30.
    instant = datetime(2026, 7, 1, 3, 30, tzinfo=UTC)

    assert to_company_time(instant).utcoffset() == timedelta(hours=-4)
    assert work_date_for(instant) == date(2026, 6, 30)


def test_device_timezone_does_not_affect_work_date():
    # Same instant reported by a phone set to UTC+9 and to UTC.
    tokyo = datetime(2026, 11, 6, 12, 30, tzinfo=timezone(timedelta(hours=9)))
    utc = tokyo.astimezone(UTC)

    assert work_date_for(tokyo) == work_date_for(utc) == date(2026, 11, 5)


def test_company_timezone_is_configurable(settings):
    settings.COMPANY_TIME_ZONE = "America/Vancouver"
    instant = datetime(2026, 11, 6, 6, 30, tzinfo=UTC)  # 22:30 PST, Nov 5

    assert work_date_for(instant) == date(2026, 11, 5)


def test_naive_datetimes_are_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        work_date_for(datetime(2026, 11, 6, 8, 0))
