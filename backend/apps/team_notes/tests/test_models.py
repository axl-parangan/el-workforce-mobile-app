import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.accounts.models import Role
from apps.team_notes.models import JobNote

pytestmark = pytest.mark.django_db


@pytest.fixture
def leadhand(make_user):
    return make_user(role=Role.LEADHAND)


def test_note_belongs_to_a_job_and_records_author_and_timestamps(make_job, leadhand):
    note = JobNote.objects.create(job=make_job(), author=leadhand, content="Delivery at 7am.")

    assert note.created_at is not None
    assert note.updated_at is not None
    assert note.is_deleted is False


def test_soft_deleted_notes_are_kept_but_hidden(make_job, leadhand):
    job = make_job()
    kept = JobNote.objects.create(job=job, author=leadhand, content="Keep")
    gone = JobNote.objects.create(job=job, author=leadhand, content="Remove")
    gone.deleted_at, gone.deleted_by = timezone.now(), leadhand
    gone.save()

    assert list(job.notes.visible()) == [kept]
    assert job.notes.count() == 2


def test_soft_delete_requires_who_and_when(make_job, leadhand):
    with pytest.raises(IntegrityError):
        JobNote.objects.create(
            job=make_job(), author=leadhand, content="x", deleted_at=timezone.now()
        )


def test_note_content_cannot_be_empty(make_job, leadhand):
    with pytest.raises(IntegrityError):
        JobNote.objects.create(job=make_job(), author=leadhand, content="")
