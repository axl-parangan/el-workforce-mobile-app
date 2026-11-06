from django.contrib import admin

from common.admin import ReadOnlyModelAdmin

from .models import JobNote


@admin.register(JobNote)
class JobNoteAdmin(ReadOnlyModelAdmin):
    """Inspection only: edits and soft deletes go through team_notes services."""

    list_display = ("job", "author", "created_at", "updated_at", "deleted_at")
    list_filter = (("deleted_at", admin.EmptyFieldListFilter),)
    search_fields = ("content", "job__job_number", "author__email")
