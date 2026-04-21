"""RSA decrypt tool: private key is kept in the browser (localStorage), not Django session.

Decrypt POST sends PEM + ciphertext once; the server does not persist either.
"""

from __future__ import annotations

import base64
import binascii
import re

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from django.contrib import messages
from django.shortcuts import redirect
from django.views.decorators.http import require_http_methods

from core.decorators import staff_member_required
from core.htmx_navigation import render_page_or_shell

MAX_KEY_BYTES = 256 * 1024


def _parse_ciphertext(raw: str) -> bytes | None:
    text = (raw or "").strip()
    if not text:
        return None
    compact = re.sub(r"\s+", "", text)
    try:
        return base64.b64decode(compact, validate=True)
    except binascii.Error:
        pass
    if re.fullmatch(r"[0-9a-fA-F]+", compact) and len(compact) % 2 == 0:
        try:
            return bytes.fromhex(compact)
        except ValueError:
            return None
    try:
        return base64.b64decode(text)
    except binascii.Error:
        return None


def _try_decrypt(pem: str, ciphertext: bytes) -> tuple[str | None, str | None]:
    try:
        key = serialization.load_pem_private_key(
            pem.encode("utf-8"),
            password=None,
        )
    except Exception as exc:
        return None, f"Invalid private key PEM: {exc}"

    if not isinstance(key, rsa.RSAPrivateKey):
        return None, "Key is not an RSA private key."

    oaep_sha256 = padding.OAEP(
        mgf=padding.MGF1(algorithm=hashes.SHA256()),
        algorithm=hashes.SHA256(),
        label=None,
    )
    oaep_sha1 = padding.OAEP(
        mgf=padding.MGF1(algorithm=hashes.SHA1()),
        algorithm=hashes.SHA1(),
        label=None,
    )
    pkcs15 = padding.PKCS1v15()

    plain = None
    for pad in (oaep_sha256, oaep_sha1, pkcs15):
        try:
            plain = key.decrypt(ciphertext, pad)
            break
        except Exception:
            continue
    if plain is None:
        return None, "Decryption failed (wrong key, padding, or corrupt ciphertext)."

    try:
        return plain.decode("utf-8"), None
    except UnicodeDecodeError:
        return plain.hex(), None


@staff_member_required
@require_http_methods(["GET", "POST"])
def rsa_decrypt_view(request):
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action != "decrypt":
            return redirect("tools:rsa_decrypt")

        pem = (request.POST.get("private_key_pem") or "").strip()
        if not pem:
            messages.error(
                request,
                "No private key: load a PEM file in the browser (stored locally until you clear or replace it).",
            )
            return redirect("tools:rsa_decrypt")
        if len(pem.encode("utf-8")) > MAX_KEY_BYTES:
            messages.error(request, "Private key text is too large.")
            return redirect("tools:rsa_decrypt")

        ct_bytes = _parse_ciphertext(request.POST.get("ciphertext", ""))
        if not ct_bytes:
            messages.error(request, "Paste ciphertext as Base64 (or hex).")
            return redirect("tools:rsa_decrypt")

        plain, err = _try_decrypt(pem, ct_bytes)
        if err:
            messages.error(request, err)
            return redirect("tools:rsa_decrypt")

        ctx = {"decrypted_plaintext": plain}
        return render_page_or_shell(
            request,
            full_template="tools/rsa_decrypt.html",
            shell_template="tools/partials/shell/rsa_decrypt.html",
            context=ctx,
        )

    ctx = {"decrypted_plaintext": None}
    return render_page_or_shell(
        request,
        full_template="tools/rsa_decrypt.html",
        shell_template="tools/partials/shell/rsa_decrypt.html",
        context=ctx,
    )
