"""
API key lookup digests: HMAC-SHA256 with SECRET_KEY (keyed), plus legacy SHA-256 for migration.

**Legacy path:** Rows created before HMAC migration used unsalted SHA-256 in
``api_key_lookup_hash``. ``_resolve_api_user`` still accepts those digests until
every row is backfilled (see migration).

**Hidden storage:** After regenerate, ``api_key`` holds a non-secret placeholder
(``HIDDEN_API_KEY_PREFIX``); only the HMAC digest is used for authentication.
"""

from __future__ import annotations

import hashlib
import hmac

from django.conf import settings

HIDDEN_API_KEY_PREFIX = "__hk__"


def _secret_bytes() -> bytes:
    return settings.SECRET_KEY.encode("utf-8")


def api_key_hmac_digest(raw: str) -> str:
    return hmac.new(_secret_bytes(), raw.encode("utf-8"), hashlib.sha256).hexdigest()


def legacy_api_key_sha256_digest(raw: str) -> str:
    """Pre-migration lookup hash (unsalted SHA-256 hex); kept for transitional verification."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def is_hidden_api_key_storage(api_key: str) -> bool:
    return bool(api_key and api_key.startswith(HIDDEN_API_KEY_PREFIX))
