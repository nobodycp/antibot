from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from dashboard.cloudflare_token_crypto import encrypt_cloudflare_token
from dashboard.models import UserCloudflareDomain
from tools.services.cloudflare_sync_service import DomainSyncResult

User = get_user_model()


class CloudflareDomainPermissionTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=False)
        self.user_a = User.objects.create_user(username="user_a", password="pass-a")
        self.user_b = User.objects.create_user(username="user_b", password="pass-b")
        self.superuser = User.objects.create_user(
            username="super_u",
            password="pass-s",
            is_superuser=True,
            is_staff=True,
        )
        self.domain_b = UserCloudflareDomain.objects.create(
            user=self.user_b,
            domain_name="b.example.com",
            zone_id="zone-b",
            api_token_ciphertext=encrypt_cloudflare_token(self.user_b.id, "token-b"),
        )

    def test_user_cannot_delete_another_users_domain(self):
        self.client.force_login(self.user_a)
        url = reverse("tools:cloudflare_domain_delete", args=[self.domain_b.id])
        r = self.client.post(url)
        self.assertEqual(r.status_code, 404)
        self.assertTrue(UserCloudflareDomain.objects.filter(pk=self.domain_b.pk).exists())

    @patch(
        "tools.views.cloudflare_domains_views.verify_cloudflare_zone",
        return_value=(True, "", ""),
    )
    def test_user_cannot_update_another_users_domain(self, _mock_verify):
        self.client.force_login(self.user_a)
        url = reverse("tools:cloudflare_domain_update", args=[self.domain_b.id])
        r = self.client.post(
            url,
            {
                "domain_name": "hacked.example.com",
                "zone_id": "zone-x",
            },
        )
        self.assertEqual(r.status_code, 404)
        self.domain_b.refresh_from_db()
        self.assertEqual(self.domain_b.domain_name, "b.example.com")

    def test_logged_in_user_can_access_own_domains_page(self):
        self.client.force_login(self.user_a)
        url = reverse("tools:cloudflare_domains")
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)

    def test_non_superuser_cannot_access_admin_user_domains(self):
        self.client.force_login(self.user_a)
        url = reverse("dashboard:user_domains", args=[self.user_b.id])
        r = self.client.get(url)
        self.assertEqual(r.status_code, 302)

    def test_superuser_can_access_admin_user_domains(self):
        self.client.force_login(self.superuser)
        url = reverse("dashboard:user_domains", args=[self.user_b.id])
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "b.example.com")

    @patch("tools.views.cloudflare_domains_views.sync_domain")
    def test_user_can_sync_own_domain(self, mock_sync):
        domain_a = UserCloudflareDomain.objects.create(
            user=self.user_a,
            domain_name="a.example.com",
            zone_id="zone-a",
            api_token_ciphertext=encrypt_cloudflare_token(self.user_a.id, "token-a"),
        )
        mock_sync.return_value = DomainSyncResult(
            domain_id=domain_a.pk,
            domain_name=domain_a.domain_name,
            ok=True,
            status=UserCloudflareDomain.SYNC_OK,
            message="Synced successfully.",
        )
        self.client.force_login(self.user_a)
        url = reverse("tools:cloudflare_domain_sync", args=[domain_a.id])
        r = self.client.post(url)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], reverse("tools:cloudflare_domains"))
        mock_sync.assert_called_once()
        self.assertEqual(mock_sync.call_args[0][0].pk, domain_a.pk)

    @patch("tools.views.cloudflare_domains_views.sync_domain")
    def test_user_cannot_sync_another_users_domain(self, mock_sync):
        self.client.force_login(self.user_a)
        url = reverse("tools:cloudflare_domain_sync", args=[self.domain_b.id])
        r = self.client.post(url)
        self.assertEqual(r.status_code, 404)
        mock_sync.assert_not_called()

    @patch("dashboard.views.user_domains_views.sync_domain")
    def test_superuser_can_sync_user_domain_via_admin(self, mock_sync):
        mock_sync.return_value = DomainSyncResult(
            domain_id=self.domain_b.pk,
            domain_name=self.domain_b.domain_name,
            ok=True,
            status=UserCloudflareDomain.SYNC_OK,
            message="Synced successfully.",
        )
        self.client.force_login(self.superuser)
        url = reverse(
            "dashboard:user_domain_sync",
            args=[self.user_b.id, self.domain_b.id],
        )
        r = self.client.post(url)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(
            r["Location"],
            reverse("dashboard:user_domains", args=[self.user_b.id]),
        )
        mock_sync.assert_called_once()

    def test_non_superuser_cannot_sync_via_admin_endpoint(self):
        domain_a = UserCloudflareDomain.objects.create(
            user=self.user_a,
            domain_name="a.example.com",
            zone_id="zone-a",
            api_token_ciphertext=encrypt_cloudflare_token(self.user_a.id, "token-a"),
        )
        self.client.force_login(self.user_a)
        url = reverse(
            "dashboard:user_domain_sync",
            args=[self.user_a.id, domain_a.id],
        )
        r = self.client.post(url)
        self.assertEqual(r.status_code, 302)

    def test_domains_list_shows_per_row_sync_button(self):
        UserCloudflareDomain.objects.create(
            user=self.user_a,
            domain_name="a.example.com",
            zone_id="zone-a",
            api_token_ciphertext=encrypt_cloudflare_token(self.user_a.id, "token-a"),
        )
        self.client.force_login(self.user_a)
        r = self.client.get(reverse("tools:cloudflare_domains"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Sync")
        self.assertNotContains(r, "Sync All")
