"""Every registered admin page renders (catches broken list_display/fieldsets)."""

import pytest
from django.contrib import admin
from django.urls import reverse

from apps.accounts.models import User

MODELS = sorted(admin.site._registry, key=lambda model: model._meta.label)


@pytest.fixture
def admin_client(client, db):
    client.force_login(User.objects.create_superuser(email="root@example.com", password="x"))
    return client


@pytest.mark.parametrize("model", MODELS, ids=lambda model: model._meta.label)
def test_admin_changelist_renders(admin_client, model):
    opts = model._meta
    response = admin_client.get(reverse(f"admin:{opts.app_label}_{opts.model_name}_changelist"))

    assert response.status_code == 200


@pytest.mark.parametrize("model", MODELS, ids=lambda model: model._meta.label)
def test_admin_add_page_renders_when_adding_is_allowed(admin_client, model, rf):
    opts = model._meta
    request = rf.get("/")
    request.user = User.objects.get(email="root@example.com")
    if not admin.site._registry[model].has_add_permission(request):
        pytest.skip("adding is disabled for this model")

    response = admin_client.get(reverse(f"admin:{opts.app_label}_{opts.model_name}_add"))

    assert response.status_code == 200
