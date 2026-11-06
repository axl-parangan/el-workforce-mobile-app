from django.db import models


class PunchType(models.TextChoices):
    CLOCK_IN = "clock_in", "Clock in"
    CLOCK_OUT = "clock_out", "Clock out"


class BatchSource(models.TextChoices):
    """How the batch reached the server (assumption; see docs/development/data-model.md)."""

    MOBILE_ONLINE = "mobile_online", "Mobile (online)"
    MOBILE_OFFLINE_SYNC = "mobile_offline_sync", "Mobile (synced after offline capture)"
    ADMIN_ENTRY = "admin_entry", "Entered by an Admin"


class LocationStatus(models.TextChoices):
    """Outcome of services.location_validation.assess_punch_location (ADR 004)."""

    VERIFIED = "verified", "Verified on site"
    INVALID_COORDINATES = "invalid_coordinates", "Invalid coordinates (discarded)"
    LOCATION_UNAVAILABLE = "location_unavailable", "No location captured"
    OUTSIDE_GEOFENCE = "outside_geofence", "Outside job geofence"
    LOW_ACCURACY = "low_accuracy", "GPS accuracy too low"
    ACCURACY_UNKNOWN = "accuracy_unknown", "GPS accuracy missing or invalid"
    GEOFENCE_NOT_CONFIGURED = "geofence_not_configured", "Job has no geofence"


class BatchItemResult(models.TextChoices):
    PENDING = "pending", "Pending"
    ACCEPTED = "accepted", "Accepted"
    REJECTED = "rejected", "Rejected"


class ItemResultCode(models.TextChoices):
    """Machine-readable outcome stored on each batch item; retries return it verbatim."""

    # Accepted
    CLOCKED_IN = "clocked_in", "Clocked in"
    CLOCKED_OUT = "clocked_out", "Clocked out"
    # Rejected: employee or job not eligible
    EMPLOYEE_INACTIVE = "employee_inactive", "Employee is inactive"
    JOB_NOT_ACTIVE = "job_not_active", "Job is not active"
    NO_ACTIVE_ASSIGNMENT = "no_active_assignment", "No active assignment to the job"
    ASSIGNMENT_NOT_IN_EFFECT = "assignment_not_in_effect", "Assignment not in effect on that date"
    # Rejected: attendance state
    ALREADY_CLOCKED_IN = "already_clocked_in", "Already clocked in"
    NO_OPEN_SESSION = "no_open_session", "No open session to clock out of"
    OPEN_SESSION_ON_OTHER_JOB = "open_session_on_other_job", "Clocked in to a different job"
    CLOCK_OUT_BEFORE_CLOCK_IN = "clock_out_before_clock_in", "Clock-out is before the clock-in"
    OVERLAPS_EXISTING_SESSION = "overlaps_existing_session", "Overlaps an existing session"


ACCEPTED_RESULT_CODES = (ItemResultCode.CLOCKED_IN, ItemResultCode.CLOCKED_OUT)


class SessionExceptionFlag(models.TextChoices):
    """Why a work session needs review. Stored without duplicates on WorkSession."""

    # From the location assessment of either punch (ADR 004).
    INVALID_COORDINATES = "invalid_coordinates", "Invalid coordinates (discarded)"
    LOCATION_UNAVAILABLE = "location_unavailable", "No location captured"
    OUTSIDE_GEOFENCE = "outside_geofence", "Outside job geofence"
    LOW_ACCURACY = "low_accuracy", "GPS accuracy too low"
    ACCURACY_UNKNOWN = "accuracy_unknown", "GPS accuracy missing or invalid"
    # From attendance processing.
    FUTURE_TIMESTAMP = "future_timestamp", "Device time is ahead of server time"
    CLOCK_OUT_REJECTED = "clock_out_rejected", "A clock-out could not be reconciled"


class SessionStatus(models.TextChoices):
    OPEN = "open", "Open (clocked in)"
    CLOSED = "closed", "Closed (clocked out)"


class ReviewStatus(models.TextChoices):
    NOT_REQUIRED = "not_required", "Not required"
    PENDING = "pending", "Pending review"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class ReviewDecision(models.TextChoices):
    APPROVED = ReviewStatus.APPROVED.value, "Approved"
    REJECTED = ReviewStatus.REJECTED.value, "Rejected"
