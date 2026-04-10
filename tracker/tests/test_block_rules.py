from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from tracker.models import BlockedIP


class AddBlockRuleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="test-pass-123",
        )
        self.client.force_login(self.user)

    def test_add_block_rule_creates_blocked_ip(self):
        ip = "198.51.100.44"
        url = reverse("tracker:add_block_rule")
        self.assertFalse(BlockedIP.objects.filter(ip_address=ip).exists())

        response = self.client.post(
            url,
            {"block_type": "ip", "block_value": ip},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("tracker:denied_logs"))
        self.assertTrue(BlockedIP.objects.filter(ip_address=ip).exists())
