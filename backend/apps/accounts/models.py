"""Authentication identity (ADR 007).

``User`` is a *login identity* plus its application role. It is not the
employee: employment data lives on ``workforce.Employee``, which links to
``User`` through an optional one-to-one relation (``user.employee``).
Not every employee has a user account, but every account created through
``apps.accounts.services.accounts`` gets an Employee record (ADR 011).
"""

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models.functions import Lower


class Role(models.TextChoices):
    """Application roles (ADR 011). A user holds exactly one.

    What each role may do is defined only in ``apps/accounts/authorization.py``;
    other code asks for a capability instead of comparing role names.

    The Employee role keeps its original stored value ``worker`` (only the
    display label changed), so no data migration or API change was needed.
    """

    ADMIN = "admin", "Admin"
    MANAGER = "manager", "Manager"
    LEADHAND = "leadhand", "LeadHand"
    WORKER = "worker", "Employee"


def normalize_email_address(email: str) -> str:
    """Emails are stored and compared lowercase so login is case-insensitive."""
    return email.strip().lower()


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address.")
        user = self.model(email=normalize_email_address(email), **extra_fields)
        # A None password produces an unusable password (account set up later).
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", Role.ADMIN)
        if extra_fields["is_staff"] is not True or extra_fields["is_superuser"] is not True:
            raise ValueError("Superuser must have is_staff=True and is_superuser=True.")
        return self._create_user(email, password, **extra_fields)

    def get_by_natural_key(self, email: str):
        # Used by ModelBackend during login.
        return self.get(email=normalize_email_address(email))


class User(AbstractUser):
    """Custom user model that logs in with email and password.

    Other login methods (phone, employee number) can be added later as extra
    authentication backends without changing this model's identity.
    """

    username = None
    email = models.EmailField("email address", unique=True)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.WORKER)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"
        constraints = [
            # Guards against case variants written through paths that bypass save().
            models.UniqueConstraint(Lower("email"), name="accounts_user_email_ci_unique"),
        ]

    def __str__(self) -> str:
        return self.email

    def save(self, *args, **kwargs) -> None:
        if self.email:
            self.email = normalize_email_address(self.email)
        super().save(*args, **kwargs)
