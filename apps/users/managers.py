from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    use_in_migrations = True

    def normalize_identity(self, email):
        if not email:
            raise ValueError("Email is required")
        return self.normalize_email(email.strip()).casefold()

    def get_by_natural_key(self, username):
        """Use the same canonicalization for login and registration."""
        return self.get(**{self.model.USERNAME_FIELD: self.normalize_identity(username)})

    def create_user(self, email, password=None, **extra_fields):
        user = self.model(email=self.normalize_identity(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("email_verified", True)
        if extra_fields["is_staff"] is not True or extra_fields["is_superuser"] is not True:
            raise ValueError("Superuser requires is_staff=True and is_superuser=True")
        if extra_fields["email_verified"] is not True:
            raise ValueError("Superuser requires email_verified=True")
        if extra_fields["is_active"] is not True:
            raise ValueError("Superuser requires is_active=True")
        return self.create_user(email, password, **extra_fields)
