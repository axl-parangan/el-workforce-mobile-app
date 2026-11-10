"""Shared fixtures for timekeeping API tests.

Timestamps are fixed past instants (never "now") so tests do not depend on
the system date. Toronto is on EDT (UTC-4) on 2026-03-10.
"""

import uuid
from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import Role

SITE = {"latitude": Decimal("43.642600"), "longitude": Decimal("-79.387100")}
# ~55.6 m north of the site centre: inside the default 100 m geofence.
INSIDE = {"latitude": "43.643100", "longitude": "-79.387100", "accuracy_meters": 10}
# ~111 m north: outside the 100 m geofence.
OUTSIDE = {"latitude": "43.643600", "longitude": "-79.387100", "accuracy_meters": 10}

MORNING = "2026-03-10T08:00:00-04:00"
NOON = "2026-03-10T12:00:00-04:00"
AFTERNOON = "2026-03-10T13:00:00-04:00"
EVENING = "2026-03-10T17:00:00-04:00"


def url(name: str, **kwargs) -> str:
    namespace = "staff_attendance" if name.startswith("staff:") else "timekeeping"
    return reverse(f"v1:{namespace}:{name.removeprefix('staff:')}", kwargs=kwargs or None)


@pytest.fixture
def client_for():
    def _client_for(user) -> APIClient:
        client = APIClient()
        client.force_authenticate(user)
        return client

    return _client_for


@pytest.fixture
def leadhand(make_employee):
    return make_employee(role=Role.LEADHAND, name="Lee Lead")


@pytest.fixture
def worker(make_employee):
    return make_employee(role=Role.WORKER, name="Wendy Worker")


@pytest.fixture
def job(make_job, make_assignment, leadhand):
    """Led by ``leadhand``, who is also actively assigned to it, so they manage it."""
    job = make_job(job_number="J-100", lead_hand=leadhand, **SITE)
    make_assignment(employee=leadhand, job=job)
    return job


@pytest.fixture
def other_job(make_job, make_assignment, leadhand):
    job = make_job(job_number="J-200", lead_hand=leadhand, **SITE)
    make_assignment(employee=leadhand, job=job)
    return job


@pytest.fixture
def assign(make_assignment):
    def _assign(employee, job, **fields):
        return make_assignment(employee=employee, job=job, **fields)

    return _assign


@pytest.fixture
def worker_client(client_for, worker, job, assign):
    assign(worker, job)
    return client_for(worker.user)


@pytest.fixture
def leadhand_client(client_for, leadhand):
    return client_for(leadhand.user)


@pytest.fixture
def admin_client(client_for, make_user):
    return client_for(make_user(role=Role.ADMIN))


def event(job, captured_at=MORNING, location=INSIDE, **extra) -> dict:
    payload = {
        "event_id": str(uuid.uuid4()),
        "job_id": job.pk,
        "captured_at": captured_at,
        "location": location,
    }
    payload.update(extra)
    return payload
