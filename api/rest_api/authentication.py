from django.conf import settings
from rest_framework import authentication, exceptions


class APIKeyUser:
    """Lightweight non-DB user object for API key authentication."""

    is_authenticated = True
    is_active = True

    def __str__(self):
        return "APIKeyUser"


class APIKeyAuthentication(authentication.BaseAuthentication):
    """
    Authenticates requests with an `Authorization: Api-Key <key>` header.

    Returns None when the header is absent (allows composing with other auth classes).
    Raises AuthenticationFailed when the header is present but the key is invalid.
    """

    keyword = "Api-Key"

    def authenticate(self, request):
        auth_header = authentication.get_authorization_header(request).decode("utf-8")

        if not auth_header:
            return None

        parts = auth_header.split(" ", 1)
        if len(parts) != 2 or parts[0] != self.keyword:
            return None

        api_key = parts[1].strip()

        configured_key = getattr(settings, "LEDGER_API_KEY", None)
        if not configured_key:
            raise exceptions.AuthenticationFailed("API key not configured on server.")

        if api_key != configured_key:
            raise exceptions.AuthenticationFailed("Invalid API key.")

        return (APIKeyUser(), None)
