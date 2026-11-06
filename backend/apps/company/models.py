from django.conf import settings
from django.db import models


class CompanySettings(models.Model):
    """Single-row company configuration, editable by the Admin at runtime.

    Not part of the original ERD: required by the team-notes decision
    (ADR 009) that ``workers_can_create_notes`` is an Admin-controlled company
    setting. Future company-level toggles are added here as columns.
    """

    SINGLETON_ID = 1

    id = models.PositiveSmallIntegerField(primary_key=True, default=SINGLETON_ID, editable=False)
    workers_can_create_notes = models.BooleanField(
        default=False,
        help_text="Allow workers to create notes on jobs they are assigned to.",
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = "company settings"
        verbose_name_plural = "company settings"
        constraints = [
            models.CheckConstraint(condition=models.Q(id=1), name="company_settings_singleton"),
        ]

    def __str__(self) -> str:
        return "Company settings"

    @classmethod
    def load(cls) -> "CompanySettings":
        obj, _ = cls.objects.get_or_create(pk=cls.SINGLETON_ID)
        return obj
