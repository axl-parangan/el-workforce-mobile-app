"""Who may use the timekeeping endpoints.

Role checks only. Relationship rules ("is this LeadHand the job's LeadHand?")
are enforced in services and selectors.

Assumption (documented in docs/api/timekeeping.md): reviewer access has not
been defined in detail, so only Admins can make review decisions. LeadHands
can *view* attendance, exceptions and rejections for the jobs they lead.
Change the classes below to widen or narrow access.
"""

from common.permissions import IsAdmin, IsLeadHand, IsLeadHandOrAdmin


class CanRecordGroupAttendance(IsLeadHand):
    pass


class CanViewCrewStatus(IsLeadHandOrAdmin):
    pass


class CanViewStaffAttendance(IsLeadHandOrAdmin):
    pass


class CanReviewAttendance(IsAdmin):
    pass
