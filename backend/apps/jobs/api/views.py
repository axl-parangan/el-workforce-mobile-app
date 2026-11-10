"""Thin HTTP layer for jobs and assignments: validate, call a service or selector, serialise.

Records outside the caller's scope are 404 (indistinguishable from missing);
visible records the caller may not change are 403.
"""

from __future__ import annotations

from django.http import Http404
from rest_framework import generics, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authorization import Capability
from apps.jobs.models import Job
from apps.jobs.selectors import jobs as selectors
from apps.jobs.selectors.scope import assignments_visible_to, can_view_crew
from apps.jobs.services import assignments as assignment_services
from apps.jobs.services import jobs as job_services
from common.permissions import requires

from . import serializers as s

CanViewJobs = requires(Capability.JOBS_VIEW_ASSIGNED, Capability.JOBS_VIEW_ANY)
CanCreateJobs = requires(Capability.JOBS_CREATE)
CanEditJobs = requires(Capability.JOBS_EDIT_ANY, Capability.JOBS_EDIT_MANAGED)
CanManageAssignments = requires(Capability.ASSIGNMENTS_MANAGE)
CanViewCrew = requires(Capability.ASSIGNMENTS_MANAGE, Capability.ASSIGNMENTS_VIEW_CREW)


def _validated(serializer_class, data, **kwargs) -> dict:
    serializer = serializer_class(data=data, **kwargs)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def _visible_job_or_404(request: Request, job_id: int):
    job = selectors.visible_job(request.user, job_id)
    if job is None:
        raise Http404
    return job


def _job_response(request: Request, job: Job, status_code=status.HTTP_200_OK) -> Response:
    job = selectors.for_display(Job.objects.filter(pk=job.pk)).get()
    viewer = selectors.viewer_context(request.user, [job])
    return Response(s.job_data(job, viewer), status=status_code)


# --- Jobs ---------------------------------------------------------------------------


class JobListCreateView(generics.ListAPIView):
    def get_permissions(self):
        classes = (CanCreateJobs,) if self.request.method == "POST" else (CanViewJobs,)
        return [permission() for permission in classes]

    def get_queryset(self):
        filters = _validated(s.JobFilterSerializer, self.request.query_params)
        return selectors.job_list(self.request.user, **filters)

    def list(self, request: Request, *args, **kwargs) -> Response:
        page = self.paginate_queryset(self.get_queryset())
        viewer = selectors.viewer_context(request.user, page)
        return self.get_paginated_response([s.job_data(job, viewer) for job in page])

    def post(self, request: Request) -> Response:
        data = dict(_validated(s.JobCreateSerializer, request.data))
        lead_hand = data.pop("lead_hand_id", None)
        job = job_services.create_job(actor=request.user, data=data, lead_hand=lead_hand)
        return _job_response(request, job, status.HTTP_201_CREATED)


class JobDetailView(APIView):
    def get_permissions(self):
        classes = (CanEditJobs,) if self.request.method == "PATCH" else (CanViewJobs,)
        return [permission() for permission in classes]

    def get(self, request: Request, pk: int) -> Response:
        return _job_response(request, _visible_job_or_404(request, pk))

    def patch(self, request: Request, pk: int) -> Response:
        job = _visible_job_or_404(request, pk)
        data = _validated(s.JobUpdateSerializer, request.data, instance=job, partial=True)
        job = job_services.update_job(actor=request.user, job=job, data=dict(data))
        return _job_response(request, job)


class JobLeadHandView(APIView):
    permission_classes = (CanManageAssignments,)

    def put(self, request: Request, pk: int) -> Response:
        job = _visible_job_or_404(request, pk)
        data = _validated(s.LeadHandSerializer, request.data)
        job = job_services.designate_lead_hand(
            actor=request.user, job=job, employee=data["employee_id"]
        )
        return _job_response(request, job)


class JobAssignmentsView(generics.ListAPIView):
    """The crew (and, with ``status=all``, the assignment history) of one job."""

    def get_permissions(self):
        classes = (CanManageAssignments,) if self.request.method == "POST" else (CanViewCrew,)
        return [permission() for permission in classes]

    def _job(self):
        job = _visible_job_or_404(self.request, self.kwargs["pk"])
        if not can_view_crew(self.request.user, job):
            raise Http404
        return job

    def get_queryset(self):
        job = self._job()
        filters = _validated(s.AssignmentFilterSerializer, self.request.query_params)
        return selectors.assignment_list(self.request.user, job_id=job.pk, status=filters["status"])

    def list(self, request: Request, *args, **kwargs) -> Response:
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response([s.assignment_data(a) for a in page])

    def post(self, request: Request, pk: int) -> Response:
        job = _visible_job_or_404(request, pk)
        data = _validated(s.AssignEmployeesSerializer, request.data)
        outcomes = assignment_services.assign_employees(
            actor=request.user,
            job=job,
            employees=data["employee_ids"],
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
        )
        results = []
        for outcome in outcomes:
            assignment = outcome.assignment
            if assignment is not None:
                assignment = selectors.assignment_list(request.user, status=None).get(
                    pk=assignment.pk
                )
            results.append(
                {
                    "employee_id": outcome.employee.pk,
                    "status": "assigned" if outcome.assigned else "rejected",
                    "code": outcome.code,
                    "message": outcome.message,
                    "assignment": s.assignment_data(assignment) if assignment else None,
                }
            )
        return Response(
            {"job": {"id": job.pk, "job_number": job.job_number}, "results": results},
            status=status.HTTP_201_CREATED,
        )


# --- Assignments ------------------------------------------------------------------------


class AssignmentListView(generics.ListAPIView):
    permission_classes = (CanViewJobs,)
    own_only = False

    def get_queryset(self):
        filters = _validated(s.AssignmentFilterSerializer, self.request.query_params)
        return selectors.assignment_list(self.request.user, own_only=self.own_only, **filters)

    def list(self, request: Request, *args, **kwargs) -> Response:
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response([s.assignment_data(a) for a in page])


class MyAssignmentListView(AssignmentListView):
    """The caller's own assignments: the source for offline job caching."""

    own_only = True


def _visible_assignment_or_404(request: Request, pk: int):
    assignment = (
        assignments_visible_to(request.user)
        .select_related("job", "employee", "assigned_by__employee")
        .filter(pk=pk)
        .first()
    )
    if assignment is None:
        raise Http404
    return assignment


def _assignment_response(request: Request, assignment) -> Response:
    return Response(s.assignment_data(_visible_assignment_or_404(request, assignment.pk)))


class AssignmentDetailView(APIView):
    def get_permissions(self):
        classes = (CanManageAssignments,) if self.request.method == "PATCH" else (CanViewJobs,)
        return [permission() for permission in classes]

    def get(self, request: Request, pk: int) -> Response:
        return Response(s.assignment_data(_visible_assignment_or_404(request, pk)))

    def patch(self, request: Request, pk: int) -> Response:
        assignment = _visible_assignment_or_404(request, pk)
        data = _validated(s.AssignmentDatesSerializer, request.data, instance=assignment)
        assignment = assignment_services.update_assignment_dates(
            actor=request.user, assignment=assignment, **data
        )
        return _assignment_response(request, assignment)


class AssignmentEndView(APIView):
    permission_classes = (CanManageAssignments,)

    def post(self, request: Request, pk: int) -> Response:
        assignment = _visible_assignment_or_404(request, pk)
        data = _validated(s.EndAssignmentSerializer, request.data)
        assignment = assignment_services.end_assignment(
            actor=request.user, assignment=assignment, end_date=data.get("end_date")
        )
        return _assignment_response(request, assignment)


class AssignmentCancelView(APIView):
    permission_classes = (CanManageAssignments,)

    def post(self, request: Request, pk: int) -> Response:
        assignment = _visible_assignment_or_404(request, pk)
        _validated(s.EmptyBodySerializer, request.data)
        assignment = assignment_services.cancel_assignment(
            actor=request.user, assignment=assignment
        )
        return _assignment_response(request, assignment)
