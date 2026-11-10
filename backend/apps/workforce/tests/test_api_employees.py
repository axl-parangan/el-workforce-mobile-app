"""Read-only employee list for Managers and Admins (M4)."""

from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import Role

pytestmark = pytest.mark.django_db

URL = reverse("v1:workforce:employee-list")


def client_for(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def people(make_employee):
    return {
        "manager": make_employee(role=Role.MANAGER, name="Max Manager"),
        "lead": make_employee(role=Role.LEADHAND, name="Lee Lead", employee_number="E-7"),
        "worker": make_employee(role=Role.WORKER, name="Wendy Worker"),
        "no_account": make_employee(role=None, name="Field Hand"),
        "inactive": make_employee(role=Role.WORKER, name="Gone Away", is_active=False),
    }


def names(response):
    return [e["name"] for e in response.json()["results"]]


@pytest.mark.parametrize("role", [Role.ADMIN, Role.MANAGER])
def test_managers_and_admins_list_employees(make_employee, people, role):
    response = client_for(make_employee(role=role).user).get(URL)

    assert response.status_code == 200
    assert {"Max Manager", "Lee Lead", "Wendy Worker", "Field Hand", "Gone Away"} <= set(
        names(response)
    )


@pytest.mark.parametrize("role", [Role.LEADHAND, Role.WORKER])
def test_leadhands_and_employees_cannot_list_employees(make_employee, role):
    assert client_for(make_employee(role=role).user).get(URL).status_code == 403


def test_anonymous_is_refused(api_client):
    assert api_client.get(URL).status_code == 401


def test_response_never_exposes_pay(people):
    people["lead"].hourly_rate = Decimal("123.4567")
    people["lead"].save()

    response = client_for(people["manager"].user).get(URL, {"search": "Lee"})

    [lead] = response.json()["results"]
    assert lead == {
        "id": people["lead"].pk,
        "name": "Lee Lead",
        "employee_number": "E-7",
        "is_active": True,
        "has_account": True,
        "account": {"role": "leadhand", "is_active": True},
    }
    assert "123.4567" not in response.content.decode()
    assert "rate" not in response.content.decode()


def test_filters(people):
    client = client_for(people["manager"].user)

    assert names(client.get(URL, {"role": "leadhand"})) == ["Lee Lead"]
    assert names(client.get(URL, {"role": "none"})) == ["Field Hand"]
    assert "Gone Away" not in names(client.get(URL, {"is_active": "true"}))
    assert names(client.get(URL, {"is_active": "false"})) == ["Gone Away"]
    assert names(client.get(URL, {"search": "e-7"})) == ["Lee Lead"]
    assert names(client.get(URL, {"search": "wendy"})) == ["Wendy Worker"]
    assert client.get(URL, {"role": "owner"}).status_code == 400


def test_results_are_paginated_and_sorted(people):
    body = client_for(people["manager"].user).get(URL, {"page_size": 2}).json()

    assert body["count"] >= 5
    assert len(body["results"]) == 2
    assert body["next"] is not None
    assert names_sorted(body["results"])


def names_sorted(results):
    names_ = [r["name"] for r in results]
    return names_ == sorted(names_)
