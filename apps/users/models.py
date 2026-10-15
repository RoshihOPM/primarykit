import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower

from .managers import UserManager


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = None
    email = models.EmailField(unique=True)
    email_verified = models.BooleanField(default=False, db_index=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("email"), name="users_email_ci_unique"),
        ]

    def save(self, *args, **kwargs):
        self.email = type(self).objects.normalize_identity(self.email)
        if not self._state.adding:
            previous = type(self).objects.filter(pk=self.pk).values_list("email", flat=True).first()
            if previous is not None and previous != self.email:
                self.email_verified = False
                if kwargs.get("update_fields") is not None:
                    kwargs["update_fields"] = set(kwargs["update_fields"]) | {"email", "email_verified"}
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.email
