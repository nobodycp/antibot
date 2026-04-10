"""Dashboard access smoke tests by role."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from dashboard.api_key_crypto import HIDDEN_API_KEY_PREFIX, api_key_hmac_digest
from dashboard.models import UserAPIKey

User = get_user_model()
_LOGIN_PREFIX = "/accounts/login"


class DashboardRoleAccessTests(TestCase):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.regular = User.objects.create_user(username="dash_user", password="pw-d-123")
        self.superuser = User.objects.create_user(
            username="dash_admin",
            password="pw-s-123",
            is_superuser=True,
            is_staff=True,
        )

    def test_regular_user_dashboard_home_loads(self):
        self.client.force_login(self.regular)
        r = self.client.get(reverse("dashboard:home"))
        self.assertEqual(r.status_code, 200)

    def test_superuser_dashboard_home_loads(self):
        self.client.force_login(self.superuser)
        r = self.client.get(reverse("dashboard:home"))
        self.assertEqual(r.status_code, 200)

    def test_regular_user_profile_settings_loads(self):
        self.client.force_login(self.regular)
        r = self.client.get(reverse("dashboard:profile_settings"))
        self.assertEqual(r.status_code, 200)

    def test_regular_user_cannot_open_users_management(self):
        self.client.force_login(self.regular)
        r = self.client.get(reverse("dashboard:users_management"))
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.url.startswith(_LOGIN_PREFIX))

    def test_superuser_users_management_loads(self):
        self.client.force_login(self.superuser)
        r = self.client.get(reverse("dashboard:users_management"))
        self.assertEqual(r.status_code, 200)


class UserAPIKeyRegenerateTests(TestCase):
    def test_regenerate_stores_hmac_and_placeholder_not_raw_key(self):
        user = User.objects.create_user(username="key_user", password="pw-k-123")
        row = UserAPIKey.objects.get(user=user)
        raw = row.regenerate()
        row.refresh_from_db()
        self.assertGreater(len(raw), 20)
        self.assertTrue(row.api_key.startswith(HIDDEN_API_KEY_PREFIX))
        self.assertEqual(row.api_key_lookup_hash, api_key_hmac_digest(raw))
