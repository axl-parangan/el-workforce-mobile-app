from django.conf import settings
from django.db import models
from django.db.models import Q


class JobNoteQuerySet(models.QuerySet):
    def visible(self) -> "JobNoteQuerySet":
        return self.filter(deleted_at__isnull=True)


class JobNote(models.Model):
    """A shared operational note on a job (ADR 009).

    Soft-deleted notes keep their row; use ``JobNote.objects.visible()`` for
    anything shown to users. Permission rules (LeadHand moderation, the
    ``workers_can_create_notes`` company setting) live in team_notes services.
    """

    job = models.ForeignKey("jobs.Job", on_delete=models.PROTECT, related_name="notes")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="job_notes"
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )

    objects = JobNoteQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(
                condition=~Q(content=""), name="team_notes_note_content_not_empty"
            ),
            models.CheckConstraint(
                condition=Q(deleted_at__isnull=True, deleted_by__isnull=True)
                | Q(deleted_at__isnull=False, deleted_by__isnull=False),
                name="team_notes_note_deleted_by_and_at_together",
            ),
        ]
        indexes = [models.Index(fields=("job", "created_at"))]

    def __str__(self) -> str:
        return f"Note on {self.job} by {self.author}"

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None
