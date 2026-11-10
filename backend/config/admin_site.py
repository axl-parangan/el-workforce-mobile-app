"""The Django admin is restricted to superusers (ADR 011).

Admins and Managers use the mobile app and API. Django admin access is never
derived from the application role, and staff status alone is not enough.
"""

from django.contrib import admin
from django.contrib.admin.apps import AdminConfig
from django.http import HttpRequest


class SuperuserAdminSite(admin.AdminSite):
    def has_permission(self, request: HttpRequest) -> bool:
        return request.user.is_active and request.user.is_superuser


class SuperuserAdminConfig(AdminConfig):
    default_site = "config.admin_site.SuperuserAdminSite"
