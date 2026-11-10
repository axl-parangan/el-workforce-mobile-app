"""Who may use the timekeeping endpoints (capability checks only).

Which records a LeadHand or Employee may touch is decided by scope selectors
(apps/jobs/selectors/scope.py) and services. Role definitions live in
apps/accounts/authorization.py.
"""

from apps.accounts.authorization import Capability
from common.permissions import requires

CanViewOwnAttendance = requires(Capability.ATTENDANCE_VIEW_OWN)

CanRecordForOthers = requires(Capability.ATTENDANCE_RECORD_ANY, Capability.ATTENDANCE_RECORD_CREW)

CanViewCrewStatus = requires(Capability.ATTENDANCE_VIEW_ANY, Capability.ATTENDANCE_VIEW_CREW)

CanViewStaffAttendance = requires(Capability.ATTENDANCE_VIEW_ANY, Capability.ATTENDANCE_VIEW_CREW)

# Admins and Managers. Reviewing one's own timesheet is refused by the service.
CanReviewAttendance = requires(Capability.ATTENDANCE_REVIEW)
