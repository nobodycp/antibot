"""Orchestrate the Node/Baileys WhatsApp validator from Django."""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal

AccountStatus = Literal["online", "offline", "pairing", "unknown"]

from django.conf import settings

_ACCOUNT_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


@dataclass
class ParsedNumberLine:
    line: str
    file_digits: str
    query_digits: str


@dataclass
class NumberSplitResult:
    to_check: list[str]
    already_verified: list[str]


@dataclass
class WhatsAppAccountInfo:
    name: str
    has_session: bool
    phone: str | None
    pairing_status: str | None
    pairing_message: str | None
    qr_data_url: str | None


def whatsapp_root() -> Path:
    return Path(settings.WHATSAPP_ROOT)


def sessions_dir() -> Path:
    return whatsapp_root() / "sessions"


def runs_dir() -> Path:
    return whatsapp_root() / "runs"


def validate_account_name(name: str) -> str:
    name = (name or "").strip()
    if not _ACCOUNT_RE.match(name):
        raise ValueError(
            "Account name must be 1–64 characters (letters, digits, underscore, hyphen)."
        )
    return name


def list_accounts() -> list[WhatsAppAccountInfo]:
    root = sessions_dir()
    if not root.is_dir():
        return []
    out: list[WhatsAppAccountInfo] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        name = entry.name
        if not _ACCOUNT_RE.match(name):
            continue
        creds = entry / "creds.json"
        pairing = _read_pairing_json(entry / "pairing.json")
        out.append(
            WhatsAppAccountInfo(
                name=name,
                has_session=creds.is_file(),
                phone=get_account_phone(name),
                pairing_status=pairing.get("status") if pairing else None,
                pairing_message=pairing.get("message") if pairing else None,
                qr_data_url=pairing.get("qr_data_url") if pairing else None,
            )
        )
    return out


def suggest_next_account_name() -> str:
    existing = {a.name for a in list_accounts()}
    idx = 1
    while True:
        candidate = f"acc_{idx}"
        if candidate not in existing:
            return candidate
        idx += 1


def _read_pairing_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _jid_to_phone(jid: str | None) -> str | None:
    """E.g. ``972595108208:1@s.whatsapp.net`` → ``972595108208``."""
    if not jid:
        return None
    user_part = jid.split("@", 1)[0]
    phone = user_part.split(":", 1)[0]
    return phone if phone.isdigit() else None


def get_account_phone(account_name: str) -> str | None:
    """Linked account phone from session files (no network probe).

    Primary source: ``sessions/<name>/creds.json`` → ``me.id`` (written after QR
    pairing). Fallback: ``connection_status.json`` ``phone`` / ``jid`` (filled when
    the status probe connects). Returns ``None`` until the session is linked.
    """
    try:
        name = validate_account_name(account_name)
    except ValueError:
        return None
    session = sessions_dir() / name
    phone = _jid_to_phone(_read_pairing_json(session / "creds.json").get("me", {}).get("id"))
    if phone:
        return phone
    conn = _read_connection_status(session / "connection_status.json")
    if conn.get("phone"):
        return str(conn["phone"])
    return _jid_to_phone(conn.get("jid"))


def _parse_iso_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        text = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        return None


def _read_connection_status(path: Path) -> dict[str, Any]:
    return _read_pairing_json(path)


def _connection_status_fresh(path: Path, max_age_seconds: int) -> bool:
    if not path.is_file():
        return False
    data = _read_connection_status(path)
    updated = _parse_iso_timestamp(data.get("updated_at"))
    if not updated:
        return False
    age = (datetime.now(timezone.utc) - updated).total_seconds()
    return age <= max(1, max_age_seconds)


def _run_status_probe(account_names: list[str], *, timeout_seconds: float = 25.0) -> bool:
    names = [validate_account_name(n) for n in account_names if n]
    if not names:
        return True
    root = whatsapp_root()
    index = root / "index.js"
    if not index.is_file():
        return False
    env = {
        "STATUS_PROBE": "1",
        "STATUS_ACCOUNTS": ",".join(names),
        "STATUS_TIMEOUT_MS": "12000",
    }
    try:
        proc = subprocess.run(
            [settings.WHATSAPP_NODE_BIN, str(index)],
            cwd=str(root),
            env=_node_env(env),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout_seconds,
            check=False,
        )
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def refresh_accounts_connection_status(
    account_names: list[str], *, max_age_seconds: int = 30
) -> None:
    """Probe accounts whose cached connection_status.json is missing or stale."""
    stale: list[str] = []
    for name in account_names:
        try:
            safe = validate_account_name(name)
        except ValueError:
            continue
        path = sessions_dir() / safe / "connection_status.json"
        if not _connection_status_fresh(path, max_age_seconds):
            stale.append(safe)
    if stale:
        _run_status_probe(stale)


def get_account_status(
    account_name: str, *, max_age_seconds: int = 30, probe_if_stale: bool = True
) -> AccountStatus:
    try:
        name = validate_account_name(account_name)
    except ValueError:
        return "unknown"

    session = sessions_dir() / name
    if not session.is_dir():
        return "unknown"

    pairing = _read_pairing_json(session / "pairing.json")
    pairing_status = pairing.get("status")
    if pairing_status in ("qr", "connecting"):
        return "pairing"

    creds = session / "creds.json"
    if not creds.is_file():
        return "offline"

    conn_path = session / "connection_status.json"
    if probe_if_stale and not _connection_status_fresh(conn_path, max_age_seconds):
        _run_status_probe([name])

    conn = _read_connection_status(conn_path)
    status = conn.get("status")
    if status in ("online", "offline", "pairing"):
        return status  # type: ignore[return-value]
    if pairing_status in ("qr", "connecting"):
        return "pairing"
    return "unknown"


def get_pairing_status(account_name: str) -> dict[str, Any]:
    name = validate_account_name(account_name)
    path = sessions_dir() / name / "pairing.json"
    data = _read_pairing_json(path)
    creds = sessions_dir() / name / "creds.json"
    if creds.is_file() and data.get("status") not in ("qr", "connecting"):
        return {
            "status": "connected",
            "message": "Session is linked.",
            "qr_data_url": None,
            "updated_at": data.get("updated_at"),
        }
    return {
        "status": data.get("status") or ("connected" if creds.is_file() else "idle"),
        "message": data.get("message", ""),
        "qr_data_url": data.get("qr_data_url"),
        "updated_at": data.get("updated_at"),
    }


def delete_account(account_name: str) -> None:
    import shutil

    name = validate_account_name(account_name)
    path = sessions_dir() / name
    if path.is_dir():
        shutil.rmtree(path)


def job_run_dir(job_id: int) -> Path:
    return runs_dir() / str(job_id)


def normalize_country_prefix(value: str) -> str:
    """Strip optional trailing colon and non-digits (e.g. `972:` → `972`)."""
    raw = (value or "").strip()
    if not raw:
        return ""
    raw = raw.rstrip(":").strip()
    return re.sub(r"\D", "", raw)


def _node_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    if extra:
        env.update(extra)
    cc = getattr(settings, "WHATSAPP_LOCAL_TRUNK_COUNTRY", "") or ""
    if cc:
        env.setdefault("LOCAL_TRUNK_COUNTRY", cc)
    return env


def _spawn_node(args: list[str], env: dict[str, str] | None = None) -> subprocess.Popen:
    root = whatsapp_root()
    index = root / "index.js"
    if not index.is_file():
        raise FileNotFoundError(f"WhatsApp validator not found at {index}")
    cmd = [settings.WHATSAPP_NODE_BIN, str(index), *args]
    return subprocess.Popen(
        cmd,
        cwd=str(root),
        env=_node_env(env),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def start_pairing(account_name: str) -> subprocess.Popen:
    name = validate_account_name(account_name)
    (sessions_dir() / name).mkdir(parents=True, exist_ok=True)
    pairing_path = sessions_dir() / name / "pairing.json"
    if pairing_path.is_file():
        pairing_path.unlink()
    return _spawn_node(
        [],
        {
            "PAIR_ONLY": "1",
            "PAIR_ACCOUNT": name,
        },
    )


def _reap_child_exit_code(pid: int | None) -> int | None:
    """Reap our direct child if it has exited; return exit code or None if still running."""
    if not pid:
        return None
    try:
        waited_pid, status = os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        # Spawned by another worker process — not our child to reap.
        return None
    except OSError:
        return None
    if waited_pid == 0:
        return None
    if os.WIFEXITED(status):
        return os.WEXITSTATUS(status)
    if os.WIFSIGNALED(status):
        return 128 + os.WTERMSIG(status)
    return -1


def is_process_running(pid: int | None) -> bool:
    if not pid:
        return False
    if _reap_child_exit_code(pid) is not None:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def terminate_process(pid: int | None) -> None:
    if not pid:
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        try:
            os.kill(pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass


def parse_numbers_text(text: str) -> list[str]:
    seen: set[str] = set()
    lines: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line in seen:
            continue
        seen.add(line)
        lines.append(line)
    return lines


def sanitize_number(raw: str) -> str | None:
    """Match Node ``sanitizeNumber`` — digits only, min length 6."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", str(raw))
    if len(digits) < 6:
        return None
    return digits


def apply_trunk_country_code(digits: str, cc: str) -> str:
    """Match Node ``applyTrunkCountryCode`` for 05X / 5X national mobiles."""
    if not cc:
        return digits
    c = re.sub(r"\D", "", str(cc))
    if not c:
        return digits
    if digits.startswith(c):
        return digits
    if len(digits) == 10 and re.fullmatch(r"05\d{8}", digits):
        return c + digits[1:]
    if len(digits) == 9 and re.fullmatch(r"5\d{8}", digits):
        return c + digits
    return digits


def parse_number_line(line: str, default_cc: str = "") -> ParsedNumberLine | None:
    """Match Node ``parseNumberLine`` (per-line CC + trunk normalization)."""
    t = (line or "").strip()
    if not t or t.startswith("#"):
        return None
    cc: str | None = None
    rest = t
    m = re.match(r"^(\d{2,4})[:/](.+)$", t)
    if m:
        cc = re.sub(r"\D", "", m.group(1))
        rest = m.group(2).strip()
    file_digits = sanitize_number(rest)
    if not file_digits:
        return None
    cc_use = cc or normalize_country_prefix(default_cc) or ""
    query_digits = apply_trunk_country_code(file_digits, cc_use)
    return ParsedNumberLine(line=line, file_digits=file_digits, query_digits=query_digits)


def normalize_numbers_list(
    lines: Iterable[str], default_cc: str = ""
) -> list[ParsedNumberLine]:
    out: list[ParsedNumberLine] = []
    seen: set[str] = set()
    for line in lines:
        parsed = parse_number_line(line, default_cc)
        if not parsed:
            continue
        if parsed.query_digits in seen:
            continue
        seen.add(parsed.query_digits)
        out.append(parsed)
    return out


def split_numbers_by_verified_history(
    lines: list[str], default_cc: str = ""
) -> NumberSplitResult:
    """Split input lines into numbers to check vs historically verified."""
    from tools.models import WhatsAppVerifiedNumber

    parsed_list = normalize_numbers_list(lines, default_cc)
    if not parsed_list:
        return NumberSplitResult([], [])

    query_digits = [p.query_digits for p in parsed_list]
    known = set(
        WhatsAppVerifiedNumber.objects.filter(phone__in=query_digits).values_list(
            "phone", flat=True
        )
    )

    to_check: list[str] = []
    already: list[str] = []
    seen_check: set[str] = set()
    seen_already: set[str] = set()
    for parsed in parsed_list:
        if parsed.query_digits in known:
            if parsed.query_digits not in seen_already:
                already.append(parsed.line)
                seen_already.add(parsed.query_digits)
        elif parsed.query_digits not in seen_check:
            to_check.append(parsed.line)
            seen_check.add(parsed.query_digits)
    return NumberSplitResult(to_check=to_check, already_verified=already)


def record_verified_from_job(job) -> int:
    """Upsert live numbers from a completed job into verified history."""
    from tools.models import WhatsAppVerifiedNumber

    cc = job.local_trunk_country or ""
    recorded = 0
    for raw in read_live_numbers(job.id):
        parsed = parse_number_line(raw, cc)
        phone = parsed.query_digits if parsed else sanitize_number(raw)
        if not phone:
            continue
        if not parsed:
            phone = apply_trunk_country_code(phone, cc)
        obj, created = WhatsAppVerifiedNumber.objects.get_or_create(
            phone=phone,
            defaults={"last_job": job},
        )
        if not created and obj.last_job_id != job.id:
            obj.last_job = job
            obj.save(update_fields=["last_job"])
        recorded += 1
    return recorded


def backfill_verified_history_from_runs() -> int:
    """Import ``verified_active_numbers.txt`` from all run directories."""
    from tools.models import WhatsAppCheckJob, WhatsAppVerifiedNumber

    recorded = 0
    root = runs_dir()
    if not root.is_dir():
        return 0
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or not entry.name.isdigit():
            continue
        job_id = int(entry.name)
        path = entry / "verified_active_numbers.txt"
        if not path.is_file():
            continue
        try:
            job = WhatsAppCheckJob.objects.get(pk=job_id)
            cc = job.local_trunk_country or ""
        except WhatsAppCheckJob.DoesNotExist:
            job = None
            cc = ""
        for raw in _read_number_lines(path):
            parsed = parse_number_line(raw, cc)
            phone = parsed.query_digits if parsed else sanitize_number(raw)
            if not phone:
                continue
            if not parsed:
                phone = apply_trunk_country_code(phone, cc)
            _, created = WhatsAppVerifiedNumber.objects.get_or_create(
                phone=phone,
                defaults={"last_job": job},
            )
            if created:
                recorded += 1
            elif job and WhatsAppVerifiedNumber.objects.filter(
                phone=phone, last_job__isnull=True
            ).exists():
                WhatsAppVerifiedNumber.objects.filter(phone=phone).update(
                    last_job=job
                )
    return recorded


def start_check_job(
    *,
    job_id: int,
    numbers: list[str],
    account_names: list[str],
    speed: str,
    fetch_presence: bool,
    local_trunk_country: str = "",
) -> subprocess.Popen:
    if not account_names:
        raise ValueError("Select at least one WhatsApp account.")
    if not numbers:
        raise ValueError("Enter at least one phone number.")

    run_path = job_run_dir(job_id)
    run_path.mkdir(parents=True, exist_ok=True)
    numbers_file = run_path / "numbers.txt"
    numbers_file.write_text("\n".join(numbers) + "\n", encoding="utf-8")

    speed_key = speed if speed in ("safe", "normal", "fast") else "normal"
    env = {
        "NON_INTERACTIVE": "1",
        "ACCOUNTS": ",".join(account_names),
        "RUN_DIR": str(run_path),
        "NUMBERS_FILE": str(numbers_file),
        "OUTPUT_FILE": str(run_path / "verified_active_numbers.txt"),
        "DETAILS_FILE": str(run_path / "verified_details.csv"),
        "PROGRESS_FILE": str(run_path / "progress.json"),
        "INVALID_FILE": str(run_path / "not_registered_numbers.txt"),
        "ERROR_NUMBERS_FILE": str(run_path / "check_error_numbers.txt"),
        "PENDING_NUMBERS_FILE": str(run_path / "pending_numbers.txt"),
        "SPEED": speed_key,
        "FETCH_PRESENCE": "1" if fetch_presence else "0",
    }
    cc = normalize_country_prefix(local_trunk_country)
    if cc:
        env["LOCAL_TRUNK_COUNTRY"] = cc
    return _spawn_node([], env)


def read_job_progress(job_id: int) -> dict[str, Any] | None:
    path = job_run_dir(job_id) / "progress.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _read_number_lines(path: Path) -> list[str]:
    if not path.is_file():
        return []
    lines: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line:
            lines.append(line)
    return lines


_ERROR_LINE_SEP = " --> "


def parse_error_number_line(line: str) -> tuple[str, str]:
    """Parse ``number --> reason`` (or legacy number-only lines)."""
    text = (line or "").strip()
    if _ERROR_LINE_SEP in text:
        number, _, reason = text.partition(_ERROR_LINE_SEP)
        return number.strip(), reason.strip()
    return text, ""


def format_error_number_line(number: str, reason: str) -> str:
    number = (number or "").strip()
    reason = (reason or "check failed").strip()
    return f"{number}{_ERROR_LINE_SEP}{reason}"


def read_live_numbers(job_id: int) -> list[str]:
    return _read_number_lines(job_run_dir(job_id) / "verified_active_numbers.txt")


def read_error_numbers(job_id: int) -> list[str]:
    """Display-ready error lines: ``number --> reason``."""
    out: list[str] = []
    for line in _read_number_lines(job_run_dir(job_id) / "check_error_numbers.txt"):
        number, reason = parse_error_number_line(line)
        if reason:
            out.append(format_error_number_line(number, reason))
        elif number:
            out.append(number)
    return out


def is_progress_complete(progress: dict[str, Any] | None) -> bool:
    if not progress:
        return False
    if progress.get("done") is True:
        return True
    totals = _progress_totals(progress)
    total = int(totals.get("total") or 0)
    checked = int(totals.get("checked") or 0)
    return total > 0 and checked >= total


def _progress_totals(progress: dict[str, Any] | None) -> dict[str, int]:
    if not progress:
        return {}
    totals = progress.get("totals")
    if isinstance(totals, dict):
        return {
            "total": int(totals.get("total") or 0),
            "checked": int(totals.get("checked") or 0),
            "live": int(totals.get("live") or 0),
            "errors": int(totals.get("errors") or 0),
            "invalid": int(totals.get("invalid") or 0),
            "pending": int(totals.get("pending") or 0),
        }
    results = progress.get("results")
    if not isinstance(results, list):
        return {}
    checked = live = errors = 0
    for row in results:
        if not isinstance(row, dict):
            continue
        checked += int(row.get("checked") or 0)
        live += int(row.get("live") or 0)
        errors += int(row.get("errors") or 0)
    invalid = max(0, checked - live - errors)
    return {
        "total": int(progress.get("total") or 0),
        "checked": checked,
        "live": live,
        "errors": errors,
        "invalid": invalid,
    }


def build_job_snapshot(job) -> dict[str, Any]:
    """Counts and number lists for the check UI (from progress.json + output files)."""
    progress = read_job_progress(job.id)
    totals = _progress_totals(progress)

    input_total = len(parse_numbers_text(job.numbers_text))
    total_count = totals.get("total") or input_total
    if input_total:
        total_count = max(int(total_count), input_total)
    valid_numbers = read_live_numbers(job.id)
    error_numbers = read_error_numbers(job.id)
    valid_count = totals.get("live") if totals else len(valid_numbers)
    error_count = totals.get("errors") if totals else job.error_count
    checked = totals.get("checked") if totals else job.checked_count
    invalid_count = totals.get("invalid") if totals else max(
        0, checked - valid_count - error_count
    )

    if not totals and job.checked_count:
        valid_count = max(valid_count, len(valid_numbers))
        error_count = max(error_count, job.error_count, len(error_numbers))
        invalid_count = max(0, job.checked_count - valid_count - error_count)

    previously_checked = list(job.previously_checked_numbers or [])
    skipped_count = len(previously_checked)

    return {
        "total_count": total_count,
        "valid_count": valid_count,
        "invalid_count": invalid_count,
        "error_count": error_count,
        "skipped_count": skipped_count,
        "valid_numbers": valid_numbers,
        "error_numbers": error_numbers,
        "previously_checked_numbers": previously_checked,
        "is_running": (
            job.status == job.STATUS_RUNNING and is_process_running(job.pid)
        ),
    }


def sync_job_from_disk(job) -> None:
    """Update job model fields from progress file and process state."""
    from tools.models import WhatsAppCheckJob

    progress = read_job_progress(job.id)
    if progress:
        totals = _progress_totals(progress)
        if totals:
            job.checked_count = totals["checked"]
            job.live_count = totals["live"]
            job.error_count = totals["errors"]
        elif isinstance(progress.get("results"), list):
            checked = live = errors = 0
            for row in progress["results"]:
                checked += int(row.get("checked") or 0)
                live += int(row.get("live") or 0)
                errors += int(row.get("errors") or 0)
            job.checked_count = checked
            job.live_count = live
            job.error_count = errors
        job.result_summary = progress

    complete = is_progress_complete(progress)
    running = is_process_running(job.pid)

    if running and not complete:
        job.status = WhatsAppCheckJob.STATUS_RUNNING
        return

    if job.status not in (
        WhatsAppCheckJob.STATUS_RUNNING,
        WhatsAppCheckJob.STATUS_PENDING,
    ):
        return

    now = datetime.now(timezone.utc)
    if complete or progress:
        was_completed = job.status == WhatsAppCheckJob.STATUS_COMPLETED
        job.status = WhatsAppCheckJob.STATUS_COMPLETED
        job.finished_at = job.finished_at or now
        job.pid = None
        if not was_completed:
            record_verified_from_job(job)
    elif job.pid:
        job.status = WhatsAppCheckJob.STATUS_FAILED
        job.error_message = job.error_message or "Validator process exited unexpectedly."
        job.finished_at = job.finished_at or now
        job.pid = None
