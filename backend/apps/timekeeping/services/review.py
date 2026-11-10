"""Review decisions on work sessions.

Each decision appends a WorkSessionReview (the audit trail) and updates the
session's latest-review summary. Punches, batches, GPS data and exception
flags are never modified.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from rest_framework import status

from apps.accounts.models import User
from apps.timekeeping.models import SessionStatus, WorkSession, WorkSessionReview
from common.exceptions import ApplicationError


class OwnTimesheetReviewError(ApplicationError):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "cannot_review_own_timesheet"


class SessionNotReviewableError(ApplicationError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "session_not_reviewable"


def review_session(
    *, session_id: int, reviewer: User, decision: str, reason: str
) -> WorkSessionReview:
    reason = reason.strip()
    if not reason:
        raise ApplicationError(
            "A reason is required.",
            code="validation_error",
            details={"reason": ["A reason is required."]},
        )

    with transaction.atomic():
        session = (
            WorkSession.objects.select_for_update(of=("self",))
            .select_related("assignment__employee")
            .get(pk=session_id)
        )
        if session.assignment.employee.user_id == reviewer.pk:
            raise OwnTimesheetReviewError(
                "You cannot review your own timesheet. Another Manager or Admin must review it.",
            )
        if session.session_status != SessionStatus.CLOSED:
            raise SessionNotReviewableError(
                "Only closed sessions can be reviewed. This session has no accepted clock-out.",
                code="session_open",
            )
        now = timezone.now()
        review = WorkSessionReview.objects.create(
            session=session, decision=decision, reason=reason, reviewed_by=reviewer, reviewed_at=now
        )
        session.review_status = decision
        session.reviewed_by = reviewer
        session.reviewed_at = now
        session.save(update_fields=["review_status", "reviewed_by", "reviewed_at", "updated_at"])
    return review
