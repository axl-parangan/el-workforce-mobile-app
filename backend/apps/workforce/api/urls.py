from django.urls import path

from .views import EmployeeListView

app_name = "workforce"

urlpatterns = [
    path("employees/", EmployeeListView.as_view(), name="employee-list"),
]
