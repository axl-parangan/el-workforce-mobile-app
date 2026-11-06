from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from common.views import HealthCheckView

api_v1_patterns = [
    path("health/", HealthCheckView.as_view(), name="health"),
    path("auth/", include("apps.accounts.api.urls")),
    path("workforce/", include("apps.workforce.api.urls")),
    path("jobs/", include("apps.jobs.api.urls")),
    path("timekeeping/", include("apps.timekeeping.api.urls")),
    path("staff/attendance/", include("apps.timekeeping.api.staff_urls")),
    path("payroll/", include("apps.payroll.api.urls")),
    path("team-notes/", include("apps.team_notes.api.urls")),
]

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("api/v1/", include((api_v1_patterns, "v1"), namespace="v1")),
]
