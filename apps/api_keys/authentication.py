"""Opt-in per-view authentication, never registered globally by the kit."""

from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from .services import verify_api_key


def scoped_api_key_authentication(required_scope: str):
    """Return an authenticator class with a fixed, explicit capability."""

    class ScopedAPIKeyAuthentication(BaseAuthentication):
        def authenticate(self, request):
            try:
                header = get_authorization_header(request).decode("ascii")
            except UnicodeDecodeError as exc:
                raise AuthenticationFailed("Invalid API key credentials") from exc
            scheme, _, token = header.partition(" ")
            if scheme.lower() != "apikey":
                return None
            if not token or " " in token:
                raise AuthenticationFailed("Invalid API key credentials")
            return verify_api_key(token, required_scope=required_scope)

        def authenticate_header(self, request):
            return "ApiKey"

    return ScopedAPIKeyAuthentication
