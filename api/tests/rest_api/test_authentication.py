from django.test import TestCase, RequestFactory, override_settings
from rest_framework.exceptions import AuthenticationFailed

from api.rest_api.authentication import APIKeyAuthentication, APIKeyUser


@override_settings(LEDGER_API_KEY="test-secret-key")
class APIKeyAuthenticationTest(TestCase):
    def setUp(self):
        self.auth = APIKeyAuthentication()
        self.factory = RequestFactory()

    def test_valid_api_key_authenticates(self):
        request = self.factory.get("/", HTTP_AUTHORIZATION="Api-Key test-secret-key")
        user, _ = self.auth.authenticate(request)
        self.assertIsInstance(user, APIKeyUser)
        self.assertTrue(user.is_authenticated)

    def test_invalid_api_key_raises(self):
        request = self.factory.get("/", HTTP_AUTHORIZATION="Api-Key wrong-key")
        with self.assertRaises(AuthenticationFailed):
            self.auth.authenticate(request)

    def test_missing_header_returns_none(self):
        request = self.factory.get("/")
        result = self.auth.authenticate(request)
        self.assertIsNone(result)

    def test_wrong_auth_scheme_returns_none(self):
        request = self.factory.get("/", HTTP_AUTHORIZATION="Bearer some-token")
        result = self.auth.authenticate(request)
        self.assertIsNone(result)

    @override_settings(LEDGER_API_KEY=None)
    def test_unconfigured_key_raises(self):
        request = self.factory.get("/", HTTP_AUTHORIZATION="Api-Key any-key")
        with self.assertRaises(AuthenticationFailed):
            self.auth.authenticate(request)

    def test_api_key_user_str(self):
        user = APIKeyUser()
        self.assertEqual(str(user), "APIKeyUser")
