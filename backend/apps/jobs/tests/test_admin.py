import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.company.models import CompanySettings
from apps.jobs.models import Job

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_user():
    return User.objects.create_superuser(email="root@example.com", password="x")


@pytest.fixture
def admin_client(client, admin_user):
    client.force_login(admin_user)
    return client


def test_creating_a_job_with_an_assignment_records_audit_users(
    admin_client, admin_user, make_employee
):
    employee = make_employee()
    prefix = "assignments"

    response = admin_client.post(
        reverse("admin:jobs_job_add"),
        {
            "job_number": "J-900",
            "name": "Warehouse fit-out",
            "status": "active",
            "geofence_radius_meters": "100",
            f"{prefix}-TOTAL_FORMS": "1",
            f"{prefix}-INITIAL_FORMS": "0",
            f"{prefix}-0-employee": str(employee.pk),
            f"{prefix}-0-status": "active",
        },
    )

    assert response.status_code == 302, response.context["adminform"].form.errors
    job = Job.objects.get(job_number="J-900")
    assert job.created_by == admin_user
    assert job.updated_by == admin_user
    assert job.assignments.get().assigned_by == admin_user


def test_admin_can_toggle_worker_note_creation(admin_client, admin_user):
    CompanySettings.load()

    response = admin_client.post(
        reverse("admin:company_companysettings_change", args=[1]),
        {"workers_can_create_notes": "on"},
    )

    assert response.status_code == 302
    settings = CompanySettings.load()
    assert settings.workers_can_create_notes is True
    assert settings.updated_by == admin_user
