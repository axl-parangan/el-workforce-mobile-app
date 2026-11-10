from django.urls import path

from . import views

app_name = "jobs"

urlpatterns = [
    path("", views.JobListCreateView.as_view(), name="list"),
    path("<int:pk>/", views.JobDetailView.as_view(), name="detail"),
    path("<int:pk>/lead-hand/", views.JobLeadHandView.as_view(), name="lead-hand"),
    path("<int:pk>/assignments/", views.JobAssignmentsView.as_view(), name="assignments"),
]
