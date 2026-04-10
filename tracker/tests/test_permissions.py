"""
Permission and ownership tests for tracker log/IP views (not the JSON API).
"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from tracker.models import IPInfo, RejectedVisitor, Visitor

User = get_user_model()

_LOGIN_PREFIX = "/accounts/login"


class TrackerOwnershipAndPermissionsTestCase(TestCase):
    """Groups 1–2 (ownership + destructive scope) and Group 3.9 (block rule access)."""

    def setUp(self):
        super().setUp()
        self.client = Client(enforce_csrf_checks=False)
        self.user_a = User.objects.create_user(username="user_a", password="pass-a-123")
        self.user_b = User.objects.create_user(username="user_b", password="pass-b-123")
        self.superuser = User.objects.create_user(
            username="super_u",
            password="pass-s-123",
            is_superuser=True,
            is_staff=True,
        )

    # --- Group 1: isolation (partials = real list endpoints) ---

    def test_user_a_cannot_see_user_b_allowed_logs_in_partial(self):
        Visitor.objects.create(
            owner=self.user_a,
            ip_address="192.0.2.10",
            os="Linux",
            browser="Firefox",
            user_agent="Mozilla/5.0",
        )
        Visitor.objects.create(
            owner=self.user_b,
            ip_address="192.0.2.20",
            os="Linux",
            browser="Chrome",
            user_agent="Mozilla/5.0",
        )
        self.client.force_login(self.user_a)
        r = self.client.get(reverse("tracker:allowed_logs_partial"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "192.0.2.10")
        self.assertNotContains(r, "192.0.2.20")

    def test_user_a_cannot_see_user_b_denied_logs_in_partial(self):
        RejectedVisitor.objects.create(
            owner=self.user_a,
            ip_address="192.0.2.30",
            reason="IP",
        )
        RejectedVisitor.objects.create(
            owner=self.user_b,
            ip_address="192.0.2.40",
            reason="IP",
        )
        self.client.force_login(self.user_a)
        r = self.client.get(reverse("tracker:denied_logs_partial"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "192.0.2.30")
        self.assertNotContains(r, "192.0.2.40")

    def test_user_a_cannot_see_user_b_ip_info_in_partial(self):
        IPInfo.objects.create(owner=self.user_a, ip_address="192.0.2.50")
        IPInfo.objects.create(owner=self.user_b, ip_address="192.0.2.51")
        self.client.force_login(self.user_a)
        r = self.client.get(reverse("tracker:ip_info_partial"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "192.0.2.50")
        self.assertNotContains(r, "192.0.2.51")

    def test_superuser_sees_all_allowed_denied_ip_info_in_partials(self):
        Visitor.objects.create(
            owner=self.user_a,
            ip_address="192.0.2.60",
            os="x",
            browser="y",
            user_agent="ua",
        )
        Visitor.objects.create(
            owner=self.user_b,
            ip_address="192.0.2.61",
            os="x",
            browser="y",
            user_agent="ua",
        )
        RejectedVisitor.objects.create(owner=self.user_a, ip_address="192.0.2.62", reason="IP")
        RejectedVisitor.objects.create(owner=self.user_b, ip_address="192.0.2.63", reason="IP")
        IPInfo.objects.create(owner=self.user_a, ip_address="192.0.2.64")
        IPInfo.objects.create(owner=self.user_b, ip_address="192.0.2.65")

        self.client.force_login(self.superuser)
        r1 = self.client.get(reverse("tracker:allowed_logs_partial"))
        self.assertContains(r1, "192.0.2.60")
        self.assertContains(r1, "192.0.2.61")
        r2 = self.client.get(reverse("tracker:denied_logs_partial"))
        self.assertContains(r2, "192.0.2.62")
        self.assertContains(r2, "192.0.2.63")
        r3 = self.client.get(reverse("tracker:ip_info_partial"))
        self.assertContains(r3, "192.0.2.64")
        self.assertContains(r3, "192.0.2.65")

    # --- Group 2: destructive scope ---

    def test_regular_user_allowed_log_delete_by_ip_only_own_rows(self):
        va1 = Visitor.objects.create(
            owner=self.user_a,
            ip_address="192.0.2.70",
            os="x",
            browser="y",
            user_agent="ua",
        )
        Visitor.objects.create(
            owner=self.user_a,
            ip_address="192.0.2.70",
            os="x",
            browser="y",
            user_agent="ua",
        )
        vb = Visitor.objects.create(
            owner=self.user_b,
            ip_address="192.0.2.70",
            os="x",
            browser="y",
            user_agent="ua",
        )
        self.client.force_login(self.user_a)
        self.client.post(
            reverse("tracker:allowed_logs"),
            {"delete_id": str(va1.pk)},
        )
        self.assertEqual(Visitor.objects.filter(owner=self.user_a, ip_address="192.0.2.70").count(), 0)
        self.assertTrue(Visitor.objects.filter(pk=vb.pk).exists())

    def test_superuser_allowed_log_delete_by_ip_removes_all_owners(self):
        va = Visitor.objects.create(
            owner=self.user_a,
            ip_address="192.0.2.71",
            os="x",
            browser="y",
            user_agent="ua",
        )
        Visitor.objects.create(
            owner=self.user_b,
            ip_address="192.0.2.71",
            os="x",
            browser="y",
            user_agent="ua",
        )
        self.client.force_login(self.superuser)
        self.client.post(
            reverse("tracker:allowed_logs"),
            {"delete_id": str(va.pk)},
        )
        self.assertEqual(Visitor.objects.filter(ip_address="192.0.2.71").count(), 0)

    def test_regular_user_denied_log_delete_by_ip_only_own_rows(self):
        ra = RejectedVisitor.objects.create(
            owner=self.user_a,
            ip_address="192.0.2.80",
            reason="IP",
        )
        rb = RejectedVisitor.objects.create(
            owner=self.user_b,
            ip_address="192.0.2.80",
            reason="IP",
        )
        self.client.force_login(self.user_a)
        self.client.post(
            reverse("tracker:denied_logs"),
            {"delete_id": str(ra.pk)},
        )
        self.assertFalse(RejectedVisitor.objects.filter(pk=ra.pk).exists())
        self.assertTrue(RejectedVisitor.objects.filter(pk=rb.pk).exists())

    def test_superuser_denied_log_delete_by_ip_removes_all_owners(self):
        ra = RejectedVisitor.objects.create(
            owner=self.user_a,
            ip_address="192.0.2.81",
            reason="IP",
        )
        RejectedVisitor.objects.create(
            owner=self.user_b,
            ip_address="192.0.2.81",
            reason="IP",
        )
        self.client.force_login(self.superuser)
        self.client.post(
            reverse("tracker:denied_logs"),
            {"delete_id": str(ra.pk)},
        )
        self.assertEqual(RejectedVisitor.objects.filter(ip_address="192.0.2.81").count(), 0)

    def test_regular_user_ip_info_delete_by_id_only_own_row(self):
        ia = IPInfo.objects.create(owner=self.user_a, ip_address="192.0.2.90")
        ib = IPInfo.objects.create(owner=self.user_b, ip_address="192.0.2.90")
        self.client.force_login(self.user_a)
        self.client.post(
            reverse("tracker:ip_info"),
            {"delete_id": str(ia.pk)},
        )
        self.assertFalse(IPInfo.objects.filter(pk=ia.pk).exists())
        self.assertTrue(IPInfo.objects.filter(pk=ib.pk).exists())

    def test_superuser_ip_info_delete_by_ip_removes_all_owners(self):
        ia = IPInfo.objects.create(owner=self.user_a, ip_address="192.0.2.91")
        IPInfo.objects.create(owner=self.user_b, ip_address="192.0.2.91")
        self.client.force_login(self.superuser)
        self.client.post(
            reverse("tracker:ip_info"),
            {"delete_id": str(ia.pk)},
        )
        self.assertEqual(IPInfo.objects.filter(ip_address="192.0.2.91").count(), 0)

    # --- Group 3.9: block rules superuser-only ---

    def test_non_superuser_cannot_access_blocked_ips_page(self):
        self.client.force_login(self.user_a)
        r = self.client.get(reverse("tracker:blocked_ips"))
        # superuser_required redirects authenticated non-superusers to LOGIN_URL by default.
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.url.startswith(_LOGIN_PREFIX))

    def test_non_superuser_cannot_post_add_block_rule(self):
        self.client.force_login(self.user_a)
        r = self.client.post(
            reverse("tracker:add_block_rule"),
            {"block_type": "ip", "block_value": "192.0.2.100"},
        )
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.url.startswith(_LOGIN_PREFIX))
