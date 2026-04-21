"""Tools app permission tests (superuser-only pages)."""

import base64

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
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


class RsaDecryptToolTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.staff = User.objects.create_user(
            username="rsa_staff",
            password="pw-staff-99",
            is_staff=True,
            is_superuser=False,
        )
        self.regular = User.objects.create_user(username="rsa_plain", password="pw-plain-99")

        priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.pem = priv.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")
        pub = priv.public_key()
        self.ciphertext_b64 = base64.b64encode(
            pub.encrypt(
                b"secret-message",
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None,
                ),
            )
        ).decode("ascii")

    def test_staff_can_open_rsa_decrypt(self):
        self.client.force_login(self.staff)
        r = self.client.get(reverse("tools:rsa_decrypt"))
        self.assertEqual(r.status_code, 200)

    def test_non_staff_redirected_from_rsa_decrypt(self):
        self.client.force_login(self.regular)
        r = self.client.get(reverse("tools:rsa_decrypt"))
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.url.startswith(_LOGIN_PREFIX))

    def test_decrypt_with_pem_in_post_body(self):
        self.client.force_login(self.staff)
        r = self.client.post(
            reverse("tools:rsa_decrypt"),
            {
                "action": "decrypt",
                "private_key_pem": self.pem,
                "ciphertext": self.ciphertext_b64,
            },
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "secret-message")

    def test_decrypt_without_pem_redirects_with_message(self):
        self.client.force_login(self.staff)
        r = self.client.post(
            reverse("tools:rsa_decrypt"),
            {"action": "decrypt", "ciphertext": self.ciphertext_b64},
        )
        self.assertEqual(r.status_code, 302)
