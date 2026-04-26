"""Tools app permission tests (superuser-only pages)."""

import base64
import os

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils.html import escape

from dashboard.models import UserStoredRSAPrivateKey
from dashboard.rsa_key_crypto import decrypt_user_rsa_pem, encrypt_user_rsa_pem

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

    def _store_account_key(self):
        UserStoredRSAPrivateKey.objects.update_or_create(
            user=self.staff,
            defaults={"fernet_ciphertext": encrypt_user_rsa_pem(self.staff.pk, self.pem)},
        )

    def test_staff_can_open_rsa_decrypt(self):
        self.client.force_login(self.staff)
        r = self.client.get(reverse("tools:rsa_decrypt"))
        self.assertEqual(r.status_code, 200)

    def test_non_staff_redirected_from_rsa_decrypt(self):
        self.client.force_login(self.regular)
        r = self.client.get(reverse("tools:rsa_decrypt"))
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.url.startswith(_LOGIN_PREFIX))

    def test_decrypt_with_account_stored_key(self):
        self.client.force_login(self.staff)
        self._store_account_key()
        r = self.client.post(
            reverse("tools:rsa_decrypt"),
            {"action": "decrypt", "ciphertext": self.ciphertext_b64},
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "secret-message")

    def _build_hybrid_v1_line(self, *, json_plain: str) -> str:
        priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pub = priv.public_key()
        pem = priv.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")
        aes_key = os.urandom(32)
        nonce = os.urandom(12)
        aes_ct = AESGCM(aes_key).encrypt(nonce, json_plain.encode("utf-8"), None)
        oaep = padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        )
        rsa_ct = pub.encrypt(aes_key, oaep)

        def u64(b: bytes) -> str:
            return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")

        line = f"1.{u64(rsa_ct)}.{u64(nonce)}.{u64(aes_ct)}"
        return pem, line

    def test_decrypt_hybrid_v1_envelope(self):
        json_body = '{"name":"Ada","card_last4":"4242"}'
        pem, line = self._build_hybrid_v1_line(json_plain=json_body)
        UserStoredRSAPrivateKey.objects.update_or_create(
            user=self.staff,
            defaults={"fernet_ciphertext": encrypt_user_rsa_pem(self.staff.pk, pem)},
        )
        self.client.force_login(self.staff)
        r = self.client.post(
            reverse("tools:rsa_decrypt"),
            {"action": "decrypt", "ciphertext": line},
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn(escape(json_body), r.content.decode())

    def test_decrypt_without_stored_key_redirects(self):
        self.client.force_login(self.staff)
        r = self.client.post(
            reverse("tools:rsa_decrypt"),
            {"action": "decrypt", "ciphertext": self.ciphertext_b64},
        )
        self.assertEqual(r.status_code, 302)

    def test_decrypt_htmx_returns_fragment_only(self):
        self.client.force_login(self.staff)
        self._store_account_key()
        r = self.client.post(
            reverse("tools:rsa_decrypt"),
            {"action": "decrypt", "ciphertext": self.ciphertext_b64},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "secret-message")
        self.assertNotContains(r, "rsa-decrypt-root")

    def test_upload_key_saves_encrypted_row(self):
        self.client.force_login(self.staff)
        up = SimpleUploadedFile("k.pem", self.pem.encode("utf-8"), content_type="application/x-pem-file")
        r = self.client.post(
            reverse("tools:rsa_decrypt"),
            {"action": "upload_key", "private_key": up},
        )
        self.assertEqual(r.status_code, 302)
        row = UserStoredRSAPrivateKey.objects.get(user=self.staff)
        self.assertTrue(row.fernet_ciphertext)
        self.assertEqual(self.pem.strip(), decrypt_user_rsa_pem(self.staff.pk, row.fernet_ciphertext).strip())
