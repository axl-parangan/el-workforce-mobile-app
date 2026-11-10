from rest_framework import serializers

from apps.accounts.models import Role
from apps.workforce.models import Employee
from apps.workforce.selectors.employees import NO_ACCOUNT


class EmployeeFilterSerializer(serializers.Serializer):
    search = serializers.CharField(required=False, max_length=100)
    role = serializers.ChoiceField(choices=[*Role.values, NO_ACCOUNT], required=False)
    is_active = serializers.BooleanField(required=False, allow_null=True, default=None)


class EmployeeListSerializer(serializers.ModelSerializer):
    """Identity and account status only. Pay rates are never exposed here."""

    has_account = serializers.SerializerMethodField()
    account = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = ("id", "name", "employee_number", "is_active", "has_account", "account")
        read_only_fields = fields

    def get_has_account(self, employee: Employee) -> bool:
        return employee.user_id is not None

    def get_account(self, employee: Employee) -> dict | None:
        user = employee.user
        if user is None:
            return None
        return {"role": user.role, "is_active": user.is_active}
