"""RSA decrypt tool: private key PEM is stored per user (encrypted at rest), not in the browser."""

from __future__ import annotations

import base64
import binascii
import re

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.views.decorators.http import require_http_methods

from core.decorators import staff_member_required
from core.htmx_navigation import render_page_or_shell
from dashboard.models import UserStoredRSAPrivateKey
from dashboard.rsa_key_crypto import decrypt_user_rsa_pem, encrypt_user_rsa_pem

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


def _is_htmx(request) -> bool:
    return (request.headers.get("HX-Request") or "").lower() == "true"


def _result_fragment_html(*, error_message: str | None = None, decrypted_plaintext: str | None = None) -> str:
    return render_to_string(
        "tools/partials/rsa_decrypt_result.html",
        {
            "error_message": error_message,
            "decrypted_plaintext": decrypted_plaintext,
        },
    )


def _has_stored_key(user) -> bool:
    return UserStoredRSAPrivateKey.objects.filter(user=user).exists()


def _get_stored_pem_plain(user) -> str | None:
    try:
        row = UserStoredRSAPrivateKey.objects.get(user=user)
    except UserStoredRSAPrivateKey.DoesNotExist:
        return None
    try:
        return decrypt_user_rsa_pem(user.pk, row.fernet_ciphertext)
    except ValueError:
        return None


@staff_member_required
@require_http_methods(["GET", "POST"])
def rsa_decrypt_view(request):
    user = request.user

    if request.method == "POST":
        action = request.POST.get("action", "")

        if action == "clear_key":
            deleted, _ = UserStoredRSAPrivateKey.objects.filter(user=user).delete()
            if deleted:
                messages.info(request, "Stored private key removed from your account.")
            else:
                messages.info(request, "No stored key to remove.")
            return redirect("tools:rsa_decrypt")

        if action == "upload_key":
            upload = request.FILES.get("private_key")
            if not upload:
                messages.error(request, "Choose a PEM private key file.")
                return redirect("tools:rsa_decrypt")
            raw = upload.read(MAX_KEY_BYTES + 1)
            if len(raw) > MAX_KEY_BYTES:
                messages.error(request, "Private key file is too large.")
                return redirect("tools:rsa_decrypt")
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                messages.error(request, "Private key file must be UTF-8 text (PEM).")
                return redirect("tools:rsa_decrypt")
            if "PRIVATE KEY" not in text or "BEGIN" not in text:
                messages.error(
                    request,
                    "File does not look like a PEM private key (expected BEGIN … PRIVATE KEY).",
                )
                return redirect("tools:rsa_decrypt")
            pem_plain = text.strip() + "\n"
            blob = encrypt_user_rsa_pem(user.pk, pem_plain)
            UserStoredRSAPrivateKey.objects.update_or_create(
                user=user,
                defaults={"fernet_ciphertext": blob},
            )
            messages.success(
                request,
                "Private key saved to your account (encrypted). Use a strong password and protect your login.",
            )
            return redirect("tools:rsa_decrypt")

        if action != "decrypt":
            return redirect("tools:rsa_decrypt")

        htmx = _is_htmx(request)
        pem = _get_stored_pem_plain(user)
        if not pem:
            msg = "No private key on your account yet. Upload a PEM file in the Private key section above."
            if htmx:
                return HttpResponse(_result_fragment_html(error_message=msg))
            messages.error(request, msg)
            return redirect("tools:rsa_decrypt")

        ct_bytes = _parse_ciphertext(request.POST.get("ciphertext", ""))
        if not ct_bytes:
            msg = "Paste ciphertext as Base64 (or hex)."
            if htmx:
                return HttpResponse(_result_fragment_html(error_message=msg))
            messages.error(request, msg)
            return redirect("tools:rsa_decrypt")

        plain, err = _try_decrypt(pem, ct_bytes)
        if err:
            if htmx:
                return HttpResponse(_result_fragment_html(error_message=err))
            messages.error(request, err)
            return redirect("tools:rsa_decrypt")

        if htmx:
            return HttpResponse(_result_fragment_html(decrypted_plaintext=plain))

        ctx = {"has_stored_key": True, "decrypted_plaintext": plain}
        return render_page_or_shell(
            request,
            full_template="tools/rsa_decrypt.html",
            shell_template="tools/partials/shell/rsa_decrypt.html",
            context=ctx,
        )

    ctx = {
        "has_stored_key": _has_stored_key(user),
        "decrypted_plaintext": None,
    }
    return render_page_or_shell(
        request,
        full_template="tools/rsa_decrypt.html",
        shell_template="tools/partials/shell/rsa_decrypt.html",
        context=ctx,
    )
