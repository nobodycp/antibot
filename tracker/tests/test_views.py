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
        self.regular = User.objects.create_user(
            username="regular",
            email="r@example.com",
            password="pw",
        )

    def test_denied_logs_get_ok_for_superuser(self):
        self.client.force_login(self.superuser)
        url = reverse("tracker:denied_logs")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_denied_logs_get_ok_for_regular_user(self):
        self.client.force_login(self.regular)
        url = reverse("tracker:denied_logs")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_denied_logs_post_redirects_for_regular_user(self):
        self.client.force_login(self.regular)
        url = reverse("tracker:denied_logs")
        response = self.client.post(url, {"delete_all": "1"})
        self.assertRedirects(response, url, fetch_redirect_response=False)
