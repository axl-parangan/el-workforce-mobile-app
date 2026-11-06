from django.urls import path

from . import views

app_name = "timekeeping"

urlpatterns = [
    path("clock-in/", views.ClockInView.as_view(), name="clock-in"),
    path("clock-out/", views.ClockOutView.as_view(), name="clock-out"),
    path("group-clock-in/", views.GroupClockInView.as_view(), name="group-clock-in"),
    path("group-clock-out/", views.GroupClockOutView.as_view(), name="group-clock-out"),
    path("sync/", views.SyncView.as_view(), name="sync"),
    path("status/", views.StatusView.as_view(), name="status"),
    path("sessions/", views.SessionListView.as_view(), name="session-list"),
    path("sessions/<int:pk>/", views.SessionDetailView.as_view(), name="session-detail"),
    path("jobs/<int:job_id>/crew/", views.CrewStatusView.as_view(), name="crew-status"),
]
