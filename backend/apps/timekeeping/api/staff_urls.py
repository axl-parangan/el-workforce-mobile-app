from django.urls import path

from . import views

app_name = "staff_attendance"

urlpatterns = [
    path("", views.StaffAttendanceListView.as_view(), name="list"),
    path("exceptions/", views.StaffExceptionListView.as_view(), name="exceptions"),
    path("rejected-events/", views.StaffRejectedEventListView.as_view(), name="rejected-events"),
    path("<int:pk>/", views.StaffSessionDetailView.as_view(), name="detail"),
    path("<int:pk>/review/", views.StaffSessionReviewView.as_view(), name="review"),
]
