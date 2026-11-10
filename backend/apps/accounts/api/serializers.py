from rest_framework import serializers

from apps.accounts.authorization import capabilities_for
from apps.accounts.models import User


class CurrentUserSerializer(serializers.ModelSerializer):
    """The signed-in user.

    ``capabilities`` comes from the central capability map, so clients decide
    which actions to offer without duplicating the role table (decision M3).
    The server still enforces every permission.
    """

    capabilities = serializers.SerializerMethodField()
    employee = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "email", "first_name", "last_name", "role", "capabilities", "employee")
        read_only_fields = fields

    def get_capabilities(self, user: User) -> list[str]:
        return sorted(capability.value for capability in capabilities_for(user))

    def get_employee(self, user: User) -> dict | None:
        employee = getattr(user, "employee", None)
        if employee is None:
            return None
        return {"id": employee.pk, "name": employee.name}
