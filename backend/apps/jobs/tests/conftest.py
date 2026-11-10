"""Fixtures for the jobs and assignments API tests."""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import Role


def url(name: str, **kwargs) -> str:
    """``url("jobs:list")`` or ``url("assignments:end", pk=1)``."""
    return reverse(f"v1:{name}", kwargs=kwargs or None)


@pytest.fixture
def client_for():
    def _client_for(user) -> APIClient:
        client = APIClient()
        client.force_authenticate(user)
        return client

    return _client_for


@pytest.fixture
def admin(make_employee):
    return make_employee(role=Role.ADMIN, name="Ada Admin")


@pytest.fixture
def manager(make_employee):
    return make_employee(role=Role.MANAGER, name="Max Manager")


@pytest.fixture
def leadhand(make_employee):
    return make_employee(role=Role.LEADHAND, name="Lee Lead")


@pytest.fixture
def worker(make_employee):
    return make_employee(role=Role.WORKER, name="Wendy Worker")


@pytest.fixture
def managed_job(make_job, make_assignment, leadhand, manager):
    """A job ``leadhand`` manages: designated AND actively assigned."""
    job = make_job(job_number="J-100", name="Warehouse", lead_hand=leadhand)
    make_assignment(employee=leadhand, job=job, assigned_by=manager.user)
    return job


@pytest.fixture
def other_job(make_job, make_employee, make_assignment, manager):
    """A job managed by a different LeadHand, with one crew member."""
    other_lead = make_employee(role=Role.LEADHAND, name="Olivia Other")
    job = make_job(job_number="J-900", name="Elsewhere", lead_hand=other_lead)
    make_assignment(employee=other_lead, job=job, assigned_by=manager.user)
    make_assignment(employee=make_employee(name="Their crew"), job=job, assigned_by=manager.user)
    return job
