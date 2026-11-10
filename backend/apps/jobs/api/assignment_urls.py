from django.urls import path

from . import views

app_name = "assignments"

urlpatterns = [
    path("", views.AssignmentListView.as_view(), name="list"),
    path("mine/", views.MyAssignmentListView.as_view(), name="mine"),
    path("<int:pk>/", views.AssignmentDetailView.as_view(), name="detail"),
    path("<int:pk>/end/", views.AssignmentEndView.as_view(), name="end"),
    path("<int:pk>/cancel/", views.AssignmentCancelView.as_view(), name="cancel"),
]
