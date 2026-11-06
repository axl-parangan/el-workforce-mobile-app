"""Offline synchronisation: process a device's queued attendance events (ADR 002).

Events are processed in their original logical order (device ``captured_at``,
then submission order), not in the order they arrived, so an offline
08:00 clock-in and 12:00 clock-out reconstruct an 08:00-12:00 session even
when both are received at 15:00.

Each event is processed in its own transaction through ``record_attendance``,
so one failing event never rolls back another, and each is individually
idempotent.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.accounts.models import User
from apps.timekeeping.models import BatchSource
from common.exceptions import ApplicationError

from .attendance import AttendanceEvent, AttendanceResult, record_attendance


@dataclass(frozen=True)
class SyncOutcome:
    """Result for one submitted event: either a processed batch or an error."""

    index: int
    event: AttendanceEvent
    result: AttendanceResult | None = None
    error: ApplicationError | None = None


def sync_attendance_events(
    *, actor: User, events: list[tuple[int, AttendanceEvent]]
) -> list[SyncOutcome]:
    """Process (submission index, event) pairs; returns outcomes in submission order."""
    ordered = sorted(events, key=lambda pair: (pair[1].captured_at, pair[0]))
    outcomes: list[SyncOutcome] = []
    for index, event in ordered:
        try:
            result = record_attendance(
                actor=actor, event=event, source=BatchSource.MOBILE_OFFLINE_SYNC
            )
        except ApplicationError as error:
            outcomes.append(SyncOutcome(index=index, event=event, error=error))
        else:
            outcomes.append(SyncOutcome(index=index, event=event, result=result))
    return sorted(outcomes, key=lambda outcome: outcome.index)
