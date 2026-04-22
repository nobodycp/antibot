"""Encrypt/decrypt per-user RSA PEM blobs at rest (Fernet key derived from SECRET_KEY + user id)."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet_for_user(user_id: int) -> Fernet:
    raw = hashlib.sha256(
        settings.SECRET_KEY.encode("utf-8")
        + b"|antibot-user-rsa-pem|"
        + str(user_id).encode("ascii")
    ).digest()
    key = base64.urlsafe_b64encode(raw)
    return Fernet(key)


def encrypt_user_rsa_pem(user_id: int, pem_plain: str) -> str:
    return _fernet_for_user(user_id).encrypt(pem_plain.encode("utf-8")).decode("ascii")


def decrypt_user_rsa_pem(user_id: int, blob: str) -> str:
    try:
        return _fernet_for_user(user_id).decrypt(blob.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Stored key could not be decrypted") from exc
