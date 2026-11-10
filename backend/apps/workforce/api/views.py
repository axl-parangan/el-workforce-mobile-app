from rest_framework import generics

from apps.accounts.authorization import Capability
from apps.workforce.selectors.employees import employee_list
from common.permissions import requires

from .serializers import EmployeeFilterSerializer, EmployeeListSerializer


class EmployeeListView(generics.ListAPIView):
    """Read-only employee list for Managers and Admins (decision M4).

    Filters: ``search`` (name or employee number), ``role`` (account role, or
    ``none`` for employees without an account), ``is_active``.
    """

    permission_classes = (requires(Capability.EMPLOYEES_VIEW_ANY),)
    serializer_class = EmployeeListSerializer

    def get_queryset(self):
        filters = EmployeeFilterSerializer(data=self.request.query_params)
        filters.is_valid(raise_exception=True)
        return employee_list(**filters.validated_data)
