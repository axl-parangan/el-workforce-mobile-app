"""Thin HTTP layer: validate input, call a service or selector, serialise the result."""

from __future__ import annotations

from django.http import Http404
from rest_framework import generics, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.timekeeping.models import BatchItemResult, ItemResultCode, PunchType
from apps.timekeeping.selectors import attendance as selectors
from apps.timekeeping.services.attendance import (
    AttendanceForbiddenError,
    AttendanceResult,
    record_attendance,
)
from apps.timekeeping.services.review import review_session
from apps.timekeeping.services.sync import sync_attendance_events
from common.exceptions import ApplicationError

from . import serializers as s
from .permissions import (
    CanRecordForOthers,
    CanReviewAttendance,
    CanViewCrewStatus,
    CanViewOwnAttendance,
    CanViewStaffAttendance,
)

# HTTP status for a rejected individual punch, by result code (default 409).
_REJECTION_STATUS = {
    ItemResultCode.EMPLOYEE_INACTIVE: status.HTTP_403_FORBIDDEN,
    ItemResultCode.NO_ACTIVE_ASSIGNMENT: status.HTTP_403_FORBIDDEN,
    ItemResultCode.ASSIGNMENT_NOT_IN_EFFECT: status.HTTP_403_FORBIDDEN,
}


class AttendanceRejectedError(ApplicationError):
    """An individual punch was processed and stored, but rejected by a business rule."""

    def __init__(self, result: AttendanceResult, body: dict) -> None:
        item = result.batch.items.all()[0]
        super().__init__(item.result_message, code=item.result_code, details={"result": body})
        self.status_code = _REJECTION_STATUS.get(item.result_code, status.HTTP_409_CONFLICT)


def _employee_or_403(user):
    employee = selectors.employee_for_user(user)
    if employee is None:
        raise AttendanceForbiddenError(
            "Your account is not linked to an employee record.", code="no_employee_profile"
        )
    return employee


def _filters(serializer_class, request: Request) -> dict:
    serializer = serializer_class(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


# --- Punching -------------------------------------------------------------------


class _SelfPunchView(APIView):
    action_type: str

    def post(self, request: Request) -> Response:
        serializer = s.SelfPunchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = record_attendance(
            actor=request.user, event=serializer.to_event(action_type=self.action_type)
        )
        body = s.batch_result_data(result.batch, replayed=result.replayed)
        if result.batch.items.all()[0].result_status == BatchItemResult.REJECTED:
            raise AttendanceRejectedError(result, body)
        return Response(body, status=status.HTTP_201_CREATED)


class ClockInView(_SelfPunchView):
    action_type = PunchType.CLOCK_IN


class ClockOutView(_SelfPunchView):
    action_type = PunchType.CLOCK_OUT


class _GroupPunchView(APIView):
    """Records attendance for other employees: LeadHands for the crew of jobs they
    manage, Admins and Managers company-wide (administrative entries).

    Returns 201 with one result per employee, including partial rejections."""

    permission_classes = (CanRecordForOthers,)
    action_type: str

    def post(self, request: Request) -> Response:
        serializer = s.GroupPunchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = record_attendance(
            actor=request.user, event=serializer.to_event(action_type=self.action_type)
        )
        return Response(
            s.batch_result_data(result.batch, replayed=result.replayed),
            status=status.HTTP_201_CREATED,
        )


class GroupClockInView(_GroupPunchView):
    action_type = PunchType.CLOCK_IN


class GroupClockOutView(_GroupPunchView):
    action_type = PunchType.CLOCK_OUT


class SyncView(APIView):
    """Offline queue upload. Always 200 with one result per submitted event."""

    def post(self, request: Request) -> Response:
        envelope = s.SyncRequestSerializer(data=request.data)
        envelope.is_valid(raise_exception=True)
        raw_events = envelope.validated_data["events"]

        results: list[dict | None] = [None] * len(raw_events)
        valid = []
        for index, raw in enumerate(raw_events):
            serializer = s.SyncEventSerializer(data=raw)
            if serializer.is_valid():
                valid.append((index, serializer.to_event()))
            else:
                results[index] = {
                    "event_id": raw.get("event_id") if isinstance(raw, dict) else None,
                    "status": "invalid",
                    "error": {
                        "code": "validation_error",
                        "message": "Invalid event.",
                        "details": serializer.errors,
                    },
                }

        for outcome in sync_attendance_events(actor=request.user, events=valid):
            if outcome.error is not None:
                results[outcome.index] = {
                    "event_id": str(outcome.event.event_id),
                    "status": "error",
                    "error": {
                        "code": outcome.error.code,
                        "message": outcome.error.message,
                        "details": outcome.error.details or None,
                    },
                }
            else:
                results[outcome.index] = {
                    "event_id": str(outcome.event.event_id),
                    "status": "processed",
                    "batch": s.batch_result_data(
                        outcome.result.batch, replayed=outcome.result.replayed
                    ),
                }
        return Response({"results": results})


# --- Own attendance -------------------------------------------------------------


class StatusView(APIView):
    permission_classes = (CanViewOwnAttendance,)

    def get(self, request: Request) -> Response:
        employee = _employee_or_403(request.user)
        session = selectors.open_session_for_employee(employee)
        return Response(
            {
                "employee": {"id": employee.pk, "name": employee.name},
                "clocked_in": session is not None,
                "open_session": s.WorkSessionSerializer(session).data if session else None,
            }
        )


class SessionListView(generics.ListAPIView):
    permission_classes = (CanViewOwnAttendance,)
    serializer_class = s.WorkSessionSerializer

    def get_queryset(self):
        employee = _employee_or_403(self.request.user)
        return selectors.sessions_for_employee(
            employee, **_filters(s.SessionFilterSerializer, self.request)
        )


class SessionDetailView(generics.RetrieveAPIView):
    permission_classes = (CanViewOwnAttendance,)
    serializer_class = s.WorkSessionSerializer

    def get_queryset(self):
        # Scoped to the caller's own sessions: anyone else's id is a 404.
        return selectors.sessions_for_employee(_employee_or_403(self.request.user))


class CrewStatusView(APIView):
    """Who on a job's crew is clocked in. For the LeadHand group-clock screen."""

    permission_classes = (CanViewCrewStatus,)

    def get(self, request: Request, job_id: int) -> Response:
        job = selectors.crew_job_for(request.user, job_id)
        if job is None:
            # Unknown job, or one outside the caller's scope: indistinguishable.
            raise Http404
        crew = [s.crew_member_data(member) for member in selectors.crew_status(job)]
        return Response({"job": {"id": job.pk, "job_number": job.job_number}, "crew": crew})


# --- Staff ----------------------------------------------------------------------


class StaffAttendanceListView(generics.ListAPIView):
    permission_classes = (CanViewStaffAttendance,)
    serializer_class = s.StaffWorkSessionSerializer
    exceptions_only = False

    def get_queryset(self):
        return selectors.staff_session_list(
            self.request.user,
            exceptions_only=self.exceptions_only,
            **_filters(s.StaffSessionFilterSerializer, self.request),
        )


class StaffExceptionListView(StaffAttendanceListView):
    exceptions_only = True


class StaffRejectedEventListView(generics.ListAPIView):
    permission_classes = (CanViewStaffAttendance,)
    serializer_class = s.RejectedEventSerializer

    def get_queryset(self):
        return selectors.staff_rejected_items(
            self.request.user, **_filters(s.RejectedEventFilterSerializer, self.request)
        )


class StaffSessionDetailView(generics.RetrieveAPIView):
    permission_classes = (CanViewStaffAttendance,)
    serializer_class = s.StaffWorkSessionSerializer

    def get_queryset(self):
        return selectors.sessions_for_display(selectors.staff_sessions_for_user(self.request.user))


class StaffSessionReviewView(APIView):
    permission_classes = (CanReviewAttendance,)

    def post(self, request: Request, pk: int) -> Response:
        if not selectors.staff_sessions_for_user(request.user).filter(pk=pk).exists():
            raise Http404
        serializer = s.ReviewInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review_session(session_id=pk, reviewer=request.user, **serializer.validated_data)
        session = selectors.sessions_for_display().get(pk=pk)
        return Response(s.StaffWorkSessionSerializer(session).data, status=status.HTTP_201_CREATED)
