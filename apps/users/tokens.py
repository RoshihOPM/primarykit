"""Purpose-specific, one-use confirmation token built on Django's signed tokens."""

from django.contrib.auth.tokens import PasswordResetTokenGenerator


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    key_salt = "primarykit.users.EmailVerificationToken"

    def _make_hash_value(self, user, timestamp):
        # Invalidated by email verification, password change or address update.
        return f"{user.pk}{user.password}{user.email}{user.email_verified}{timestamp}"


email_verification_token = EmailVerificationTokenGenerator()
