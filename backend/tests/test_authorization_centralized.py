"""Guard: role names may only be interpreted in the central authorization module.

Everything else must ask for a capability (apps/accounts/authorization.py) or
use the scope selectors. This test fails if role comparisons creep back into
services, selectors, views, serializers or models.
"""

import re
from pathlib import Path

from django.conf import settings

BACKEND = Path(settings.BASE_DIR)

# The only modules allowed to name or compare roles.
ALLOWED = {
    "apps/accounts/models.py",  # defines Role; superusers default to Admin
    "apps/accounts/authorization.py",  # the role -> capability map
}

PATTERNS = {
    "role constant": re.compile(r"\bRole\.(ADMIN|MANAGER|LEADHAND|WORKER)\b"),
    "role comparison": re.compile(r"\.role\s*(==|!=)|\.role\s+(not\s+)?in\b"),
    "role literal comparison": re.compile(r"""(==|!=)\s*["'](admin|manager|leadhand|worker)["']"""),
    "role helper": re.compile(r"\.is_(leadhand|worker|admin_role|manager)\b"),
}


def application_modules():
    for path in sorted(BACKEND.rglob("*.py")):
        relative = path.relative_to(BACKEND).as_posix()
        parts = set(path.relative_to(BACKEND).parts)
        if parts & {"migrations", "tests", ".venv", "staticfiles"}:
            continue
        if relative == "conftest.py" or relative in ALLOWED:
            continue
        yield relative, path.read_text()


def test_role_checks_are_centralised():
    offences = [
        f"{relative}:{number}: {name}: {line.strip()}"
        for relative, source in application_modules()
        for number, line in enumerate(source.splitlines(), start=1)
        for name, pattern in PATTERNS.items()
        if pattern.search(line)
    ]

    assert offences == [], (
        "Role checks found outside apps/accounts/authorization.py. "
        "Use has_capability()/requires() or the scope selectors instead:\n" + "\n".join(offences)
    )


def test_the_guard_actually_scans_application_code():
    scanned = [relative for relative, _ in application_modules()]

    assert "apps/timekeeping/services/attendance.py" in scanned
    assert "apps/timekeeping/api/views.py" in scanned
    assert "apps/jobs/selectors/scope.py" in scanned
