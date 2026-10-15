"""Require verified email for both API token and session authentication."""

from django.conf import settings
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication


def ensure_verified(user):
    if getattr(settings, "AUTH_REQUIRE_EMAIL_VERIFICATION", True) and not user.email_verified:
        raise AuthenticationFailed("Authentication credentials were not accepted.")
    return user


class VerifiedJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        return ensure_verified(super().get_user(validated_token))


class VerifiedSessionAuthentication(SessionAuthentication):
    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None:
            ensure_verified(result[0])
        return result
