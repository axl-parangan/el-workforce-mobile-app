"""DRF permission classes backed by the central capability map.

Use ``requires(...)`` in views; never compare role names here or in views.
Object-level rules ("is this employee in this LeadHand's crew?") live in
scope selectors and services. See apps/accounts/authorization.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from rest_framework.permissions import BasePermission

from apps.accounts.authorization import Capability, has_any_capability

if TYPE_CHECKING:
    from rest_framework.request import Request
    from rest_framework.views import APIView


class HasCapability(BasePermission):
    """Grants access when the user holds at least one of ``capabilities``."""

    capabilities: ClassVar[tuple[Capability, ...]] = ()

    def has_permission(self, request: Request, view: APIView) -> bool:
        return bool(self.capabilities) and has_any_capability(request.user, *self.capabilities)


def requires(*capabilities: Capability) -> type[HasCapability]:
    """A permission class granting access with any one of ``capabilities``."""
    if not capabilities:
        raise ValueError("requires() needs at least one capability")
    name = "Requires_" + "_or_".join(c.value.replace(".", "_") for c in capabilities)
    return type(name, (HasCapability,), {"capabilities": tuple(capabilities)})
