from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class DeniedLogsViewTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="su",
            email="su@example.com",
            password="pw",
        )

    def test_denied_logs_get_ok_for_superuser(self):
        self.client.force_login(self.superuser)
        url = reverse("tracker:denied_logs")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_denied_logs_redirects_when_not_superuser(self):
        user = User.objects.create_user(
            username="regular",
            email="r@example.com",
            password="pw",
        )
        self.client.force_login(user)
        url = reverse("tracker:denied_logs")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
