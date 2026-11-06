import pytest
from django.db import IntegrityError

from apps.company.models import CompanySettings

pytestmark = pytest.mark.django_db


def test_load_creates_the_single_row_with_defaults():
    settings = CompanySettings.load()

    assert settings.pk == 1
    assert settings.workers_can_create_notes is False
    assert CompanySettings.load().pk == settings.pk
    assert CompanySettings.objects.count() == 1


def test_a_second_row_is_rejected():
    CompanySettings.load()

    with pytest.raises(IntegrityError):
        CompanySettings.objects.create(id=2)
