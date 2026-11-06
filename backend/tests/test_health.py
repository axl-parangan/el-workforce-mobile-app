import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_health_check_reports_database_ok(api_client):
    response = api_client.get(reverse("v1:health"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


@pytest.mark.django_db
def test_health_check_is_served_under_api_v1(api_client):
    response = api_client.get("/api/v1/health/")

    assert response.status_code == 200


@pytest.mark.django_db
def test_unknown_api_version_is_not_routed(api_client):
    response = api_client.get("/api/v2/health/")

    assert response.status_code == 404
