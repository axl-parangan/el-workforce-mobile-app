"""Clients (ADR 010).

A client is separate from employees, LeadHands and Admins. For now it is a
standalone, view-only record with no relationships. Future client access
(e.g. viewing payroll reports) will add a link from users and jobs to clients.
"""

from django.db import models


class Client(models.Model):
    name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name
