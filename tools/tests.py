"""Tools app permission tests (superuser-only pages)."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

User = get_user_model()
_LOGIN_PREFIX = "/accounts/login"


class ToolsSuperuserOnlyTests(TestCase):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.regular = User.objects.create_user(username="tool_user", password="pw-reg-123")
        self.superuser = User.objects.create_user(
            username="tool_admin",
            password="pw-sup-123",
            is_superuser=True,
            is_staff=True,
        )

    def test_regular_user_google_safe_check_forbidden(self):
        self.client.force_login(self.regular)
        r = self.client.get(reverse("tools:google_safe_check"))
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.url.startswith(_LOGIN_PREFIX))

    def test_regular_user_redirect_check_forbidden(self):
        self.client.force_login(self.regular)
        r = self.client.get(reverse("tools:redirect_check"))
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.url.startswith(_LOGIN_PREFIX))

    def test_regular_user_file_upload_forbidden(self):
        self.client.force_login(self.regular)
        r = self.client.get(reverse("tools:uploader_files"))
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.url.startswith(_LOGIN_PREFIX))

    def test_superuser_can_access_google_safe_and_redirect(self):
        self.client.force_login(self.superuser)
        r1 = self.client.get(reverse("tools:google_safe_check"))
        self.assertEqual(r1.status_code, 200)
        r2 = self.client.get(reverse("tools:redirect_check"))
        self.assertEqual(r2.status_code, 200)
        r3 = self.client.get(reverse("tools:uploader_files"))
        self.assertEqual(r3.status_code, 200)
