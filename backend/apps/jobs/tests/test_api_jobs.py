"""Jobs API: visibility, creation, editing and LeadHand designation for all four roles."""

import pytest

from apps.accounts.models import Role
from apps.jobs.models import AssignmentStatus, Job, JobAssignment, JobStatus

from .conftest import url

pytestmark = pytest.mark.django_db


def employee_of(request, role):
    return request.getfixturevalue(role)


def job_numbers(response):
    return [job["job_number"] for job in response.json()["results"]]


# --- Listing and detail ----------------------------------------------------------------


@pytest.mark.parametrize("role", ["admin", "manager"])
def test_company_wide_roles_see_every_job(request, client_for, managed_job, other_job, role):
    client = client_for(employee_of(request, role).user)

    assert job_numbers(client.get(url("jobs:list"))) == ["J-100", "J-900"]
    assert client.get(url("jobs:detail", pk=other_job.pk)).status_code == 200


def test_leadhand_sees_only_jobs_they_are_assigned_to(client_for, leadhand, managed_job, other_job):
    client = client_for(leadhand.user)

    assert job_numbers(client.get(url("jobs:list"))) == ["J-100"]
    assert client.get(url("jobs:detail", pk=other_job.pk)).status_code == 404


def test_employee_sees_only_active_assignments(
    client_for, worker, managed_job, other_job, make_job, make_assignment
):
    make_assignment(employee=worker, job=managed_job)
    old = make_job(job_number="J-OLD")
    make_assignment(employee=worker, job=old, status=AssignmentStatus.ENDED)
    client = client_for(worker.user)

    assert job_numbers(client.get(url("jobs:list"))) == ["J-100"]
    assert client.get(url("jobs:detail", pk=old.pk)).status_code == 404
    assert client.get(url("jobs:detail", pk=other_job.pk)).status_code == 404


def test_job_response_shape_and_viewer_flags(client_for, leadhand, managed_job):
    body = client_for(leadhand.user).get(url("jobs:detail", pk=managed_job.pk)).json()

    assert body["job_number"] == "J-100"
    assert body["lead_hand"] == {"employee_id": leadhand.pk, "name": "Lee Lead"}
    assert body["viewer"]["manages_job"] is True
    assert body["viewer"]["is_lead_hand"] is True
    assert body["viewer"]["my_assignment_id"] is not None
    assert body["geofence"] == {
        "configured": False,
        "latitude": None,
        "longitude": None,
        "radius_meters": 100,
    }
    assert "email" not in str(body["created_by"])  # people are shown by name only


def test_list_filters(client_for, manager, leadhand, managed_job, other_job):
    client = client_for(manager.user)
    other_job.status = JobStatus.ON_HOLD
    other_job.save()

    assert job_numbers(client.get(url("jobs:list"), {"status": "on_hold"})) == ["J-900"]
    assert job_numbers(client.get(url("jobs:list"), {"search": "wareh"})) == ["J-100"]
    lead = client_for(leadhand.user)
    assert job_numbers(lead.get(url("jobs:list"), {"managed_by_me": "true"})) == ["J-100"]
    assert job_numbers(lead.get(url("jobs:list"), {"assigned_to_me": "true"})) == ["J-100"]
    assert client.get(url("jobs:list"), {"status": "bogus"}).status_code == 400


def test_anonymous_requests_are_refused(api_client):
    assert api_client.get(url("jobs:list")).status_code == 401


# --- Creating jobs -----------------------------------------------------------------------

NEW_JOB = {"job_number": "J-NEW", "name": "New site", "address": "1 Main St"}


@pytest.mark.parametrize("role", ["admin", "manager"])
def test_company_wide_roles_create_jobs_with_every_field(request, client_for, leadhand, role):
    actor = employee_of(request, role)

    response = client_for(actor.user).post(
        url("jobs:list"),
        {
            **NEW_JOB,
            "latitude": "43.642600",
            "longitude": "-79.387100",
            "geofence_radius_meters": 150,
            "status": "planned",
            "start_date": "2026-12-01",
            "lead_hand_id": leadhand.pk,
        },
        format="json",
    )

    assert response.status_code == 201, response.json()
    job = Job.objects.get(job_number="J-NEW")
    assert job.created_by == actor.user
    assert job.status == JobStatus.PLANNED
    assert job.lead_hand == leadhand
    # Designation creates the LeadHand's assignment, so they manage the job (Q4).
    assert JobAssignment.objects.get(job=job, status=AssignmentStatus.ACTIVE).employee == leadhand


def test_manager_created_job_without_lead_hand_has_no_assignments(client_for, manager):
    client_for(manager.user).post(url("jobs:list"), NEW_JOB, format="json")

    job = Job.objects.get(job_number="J-NEW")
    assert job.lead_hand is None
    assert not job.assignments.exists()


def test_leadhand_creating_a_job_leads_and_is_assigned_to_it(client_for, leadhand):
    response = client_for(leadhand.user).post(url("jobs:list"), NEW_JOB, format="json")

    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["lead_hand"]["employee_id"] == leadhand.pk
    assert body["viewer"]["manages_job"] is True
    assignment = JobAssignment.objects.get(job_id=body["id"])
    assert assignment.employee == leadhand
    assert assignment.assigned_by == leadhand.user
    assert assignment.status == AssignmentStatus.ACTIVE


@pytest.mark.parametrize(
    "extra",
    [
        {"latitude": "43.6", "longitude": "-79.3"},
        {"geofence_radius_meters": 500},
        {"status": "planned"},
    ],
)
def test_leadhand_cannot_set_restricted_fields_when_creating(client_for, leadhand, worker, extra):
    response = client_for(leadhand.user).post(url("jobs:list"), {**NEW_JOB, **extra}, format="json")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "field_not_editable"
    assert not Job.objects.filter(job_number="J-NEW").exists()


def test_leadhand_cannot_designate_someone_else(client_for, leadhand, make_employee):
    other = make_employee(role=Role.LEADHAND)

    response = client_for(leadhand.user).post(
        url("jobs:list"), {**NEW_JOB, "lead_hand_id": other.pk}, format="json"
    )

    assert response.status_code == 403
    assert not Job.objects.filter(job_number="J-NEW").exists()


def test_employees_cannot_create_jobs(client_for, worker):
    response = client_for(worker.user).post(url("jobs:list"), NEW_JOB, format="json")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"job_number": "J-100"}, "job_number"),  # duplicate
        ({"job_number": ""}, "job_number"),
        ({"latitude": "43.6"}, "latitude"),  # longitude missing
        ({"latitude": "95", "longitude": "0"}, "latitude"),
        ({"geofence_radius_meters": 0}, "geofence_radius_meters"),
        ({"start_date": "2026-12-02", "end_date": "2026-12-01"}, "end_date"),
        ({"colour": "red"}, "colour"),  # unknown field
    ],
)
def test_job_validation_errors(client_for, manager, managed_job, payload, field):
    response = client_for(manager.user).post(
        url("jobs:list"), {**NEW_JOB, **payload}, format="json"
    )

    assert response.status_code == 400, response.json()
    assert field in response.json()["error"]["details"]


# --- Editing jobs ------------------------------------------------------------------------


def test_leadhand_edits_allowed_fields_on_a_job_they_manage(client_for, leadhand, managed_job):
    response = client_for(leadhand.user).patch(
        url("jobs:detail", pk=managed_job.pk),
        {"name": "Renamed", "address": "2 Side St", "start_date": "2026-12-01"},
        format="json",
    )

    assert response.status_code == 200, response.json()
    managed_job.refresh_from_db()
    assert managed_job.name == "Renamed"
    assert managed_job.updated_by == leadhand.user


@pytest.mark.parametrize(
    "payload",
    [
        {"latitude": "43.6", "longitude": "-79.3"},
        {"geofence_radius_meters": 1000},
        {"status": "completed"},
        {"job_number": "J-RENAMED"},
    ],
)
def test_leadhand_cannot_edit_restricted_fields(client_for, leadhand, managed_job, payload):
    response = client_for(leadhand.user).patch(
        url("jobs:detail", pk=managed_job.pk), payload, format="json"
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "field_not_editable"


def test_leadhand_cannot_edit_a_job_they_only_work_on(
    client_for, leadhand, other_job, make_assignment
):
    make_assignment(employee=leadhand, job=other_job)  # crew, not the job's LeadHand

    response = client_for(leadhand.user).patch(
        url("jobs:detail", pk=other_job.pk), {"name": "Mine now"}, format="json"
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "job_not_editable"


def test_leadhand_cannot_edit_another_leadhands_job(client_for, leadhand, other_job):
    response = client_for(leadhand.user).patch(
        url("jobs:detail", pk=other_job.pk), {"name": "x"}, format="json"
    )

    assert response.status_code == 404


def test_designated_but_unassigned_leadhand_cannot_edit(client_for, leadhand, make_job):
    job = make_job(lead_hand=leadhand)  # designated, never assigned

    response = client_for(leadhand.user).patch(
        url("jobs:detail", pk=job.pk), {"name": "x"}, format="json"
    )

    assert response.status_code == 404  # not visible: not assigned


@pytest.mark.parametrize("role", ["admin", "manager"])
def test_company_wide_roles_edit_every_field(request, client_for, managed_job, role):
    response = client_for(employee_of(request, role).user).patch(
        url("jobs:detail", pk=managed_job.pk),
        {
            "status": "on_hold",
            "latitude": "43.642600",
            "longitude": "-79.387100",
            "geofence_radius_meters": 250,
            "job_number": "J-101",
        },
        format="json",
    )

    assert response.status_code == 200, response.json()
    managed_job.refresh_from_db()
    assert managed_job.status == JobStatus.ON_HOLD
    assert managed_job.geofence_radius_meters == 250
    assert managed_job.job_number == "J-101"


def test_partial_update_validates_against_existing_values(client_for, manager, managed_job):
    managed_job.start_date = "2026-12-10"
    managed_job.save()

    response = client_for(manager.user).patch(
        url("jobs:detail", pk=managed_job.pk), {"end_date": "2026-12-01"}, format="json"
    )

    assert response.status_code == 400
    assert "end_date" in response.json()["error"]["details"]


def test_lead_hand_cannot_be_changed_through_patch(client_for, manager, managed_job, worker):
    response = client_for(manager.user).patch(
        url("jobs:detail", pk=managed_job.pk), {"lead_hand_id": worker.pk}, format="json"
    )

    assert response.status_code == 400  # unknown field: use the lead-hand endpoint


def test_employees_cannot_edit_jobs(client_for, worker, managed_job, make_assignment):
    make_assignment(employee=worker, job=managed_job)

    response = client_for(worker.user).patch(
        url("jobs:detail", pk=managed_job.pk), {"name": "x"}, format="json"
    )

    assert response.status_code == 403


# --- LeadHand designation ----------------------------------------------------------------


@pytest.mark.parametrize("role", ["admin", "manager"])
def test_designating_a_leadhand_assigns_them(request, client_for, make_job, make_employee, role):
    job = make_job()
    new_lead = make_employee(role=Role.LEADHAND)

    response = client_for(employee_of(request, role).user).put(
        url("jobs:lead-hand", pk=job.pk), {"employee_id": new_lead.pk}, format="json"
    )

    assert response.status_code == 200, response.json()
    assert response.json()["lead_hand"]["employee_id"] == new_lead.pk
    assert JobAssignment.objects.filter(
        job=job, employee=new_lead, status=AssignmentStatus.ACTIVE
    ).exists()


def test_designating_an_already_assigned_leadhand_does_not_duplicate(
    client_for, manager, managed_job, leadhand
):
    client_for(manager.user).put(
        url("jobs:lead-hand", pk=managed_job.pk), {"employee_id": leadhand.pk}, format="json"
    )

    assert JobAssignment.objects.filter(job=managed_job, employee=leadhand).count() == 1


def test_replacing_a_leadhand_keeps_the_previous_one_on_the_crew(
    client_for, manager, managed_job, leadhand, make_employee
):
    replacement = make_employee(role=Role.LEADHAND)

    client_for(manager.user).put(
        url("jobs:lead-hand", pk=managed_job.pk), {"employee_id": replacement.pk}, format="json"
    )

    managed_job.refresh_from_db()
    assert managed_job.lead_hand == replacement
    assert JobAssignment.objects.get(job=managed_job, employee=leadhand).status == "active"


def test_clearing_the_designation(client_for, manager, managed_job, leadhand):
    response = client_for(manager.user).put(
        url("jobs:lead-hand", pk=managed_job.pk), {"employee_id": None}, format="json"
    )

    assert response.json()["lead_hand"] is None
    assert JobAssignment.objects.get(job=managed_job, employee=leadhand).status == "active"


@pytest.mark.parametrize("candidate", ["worker_role", "no_account", "inactive", "manager_role"])
def test_only_active_leadhand_accounts_can_be_designated(
    client_for, manager, managed_job, make_employee, candidate
):
    employee = {
        "worker_role": lambda: make_employee(role=Role.WORKER),
        "no_account": lambda: make_employee(role=None),
        "inactive": lambda: make_employee(role=Role.LEADHAND, is_active=False),
        "manager_role": lambda: make_employee(role=Role.MANAGER),
    }[candidate]()

    response = client_for(manager.user).put(
        url("jobs:lead-hand", pk=managed_job.pk), {"employee_id": employee.pk}, format="json"
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "not_eligible_lead_hand"


def test_designation_on_a_completed_job_is_refused(client_for, manager, make_job, leadhand):
    job = make_job(status=JobStatus.COMPLETED)

    response = client_for(manager.user).put(
        url("jobs:lead-hand", pk=job.pk), {"employee_id": leadhand.pk}, format="json"
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "job_not_assignable"


@pytest.mark.parametrize("role", ["leadhand", "worker"])
def test_leadhands_and_employees_cannot_designate(request, client_for, managed_job, role):
    response = client_for(employee_of(request, role).user).put(
        url("jobs:lead-hand", pk=managed_job.pk), {"employee_id": None}, format="json"
    )

    assert response.status_code == 403
