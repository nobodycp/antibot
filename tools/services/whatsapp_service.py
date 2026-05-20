"""Orchestrate the Node/Baileys WhatsApp validator from Django."""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import time
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


def _read_pairing_stderr(session_path: Path) -> str:
    log_path = session_path / "pairing.stderr.log"
    if not log_path.is_file():
        return ""
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
    return text[-500:] if len(text) > 500 else text


def get_pairing_status(
    account_name: str, *, pair_pid: int | None = None
) -> dict[str, Any]:
    name = validate_account_name(account_name)
    session_path = sessions_dir() / name
    path = session_path / "pairing.json"
    data = _read_pairing_json(path)
    creds = session_path / "creds.json"
    if creds.is_file() and data.get("status") not in ("qr", "connecting"):
        clear_pairing_pid(name)
        return {
            "status": "connected",
            "message": "Session is linked.",
            "qr_data_url": None,
            "updated_at": data.get("updated_at"),
        }
    status = data.get("status") or ("connected" if creds.is_file() else "idle")
    message = data.get("message", "")
    qr_data_url = data.get("qr_data_url")
    if status == "idle" and not creds.is_file():
        status = "connecting"
        message = message or "Starting pairing…"
    if (
        pair_pid
        and not is_process_running(pair_pid)
        and status in ("connecting", "idle")
        and not qr_data_url
        and not creds.is_file()
    ):
        stderr_tail = _read_pairing_stderr(session_path)
        msg = "Pairing stopped before a QR code appeared."
        if stderr_tail:
            msg = f"{msg} {stderr_tail}"
        else:
            root = whatsapp_root()
            if not (root / "node_modules").is_dir():
                msg = (
                    f"{msg} Run npm install in {root} and set NODE_BIN if needed."
                )
        return {
            "status": "error",
            "message": msg,
            "qr_data_url": None,
            "updated_at": data.get("updated_at"),
        }
    return {
        "status": status,
        "message": message,
        "qr_data_url": qr_data_url,
        "updated_at": data.get("updated_at"),
    }


def delete_account(account_name: str) -> None:
    import shutil

    name = validate_account_name(account_name)
    terminate_process(read_pairing_pid(name))
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


def _detach_process(proc: subprocess.Popen) -> int:
    """Return child PID; keep it running after the Popen object is discarded.

    Gunicorn workers must not keep subprocess.Popen handles in ``_active`` — worker
    recycle / shutdown can otherwise stop Node jobs started from a web request.
    """
    pid = proc.pid
    proc._child_created = False
    for stream in (proc.stdin, proc.stdout, proc.stderr):
        if stream is None or stream in (subprocess.DEVNULL, subprocess.PIPE):
            continue
        try:
            stream.close()
        except OSError:
            pass
    proc.stdin = proc.stdout = proc.stderr = None
    return pid


def _pairing_pid_path(session_path: Path) -> Path:
    return session_path / "pairing.pid"


def read_pairing_pid(account_name: str) -> int | None:
    try:
        name = validate_account_name(account_name)
    except ValueError:
        return None
    path = _pairing_pid_path(sessions_dir() / name)
    if not path.is_file():
        return None
    try:
        raw = path.read_text(encoding="utf-8").strip()
        return int(raw) if raw else None
    except (OSError, ValueError):
        return None


def write_pairing_pid(account_name: str, pid: int) -> None:
    name = validate_account_name(account_name)
    path = _pairing_pid_path(sessions_dir() / name)
    path.write_text(str(pid), encoding="utf-8")


def clear_pairing_pid(account_name: str) -> None:
    try:
        name = validate_account_name(account_name)
    except ValueError:
        return
    _pairing_pid_path(sessions_dir() / name).unlink(missing_ok=True)


def resolve_pairing_pid(
    account_name: str, session_pid: int | None = None
) -> int | None:
    """Pairing PID from session and/or on-disk file (survives refresh / worker change)."""
    candidates: list[int] = []
    for raw in (session_pid, read_pairing_pid(account_name)):
        if isinstance(raw, int) and raw > 0 and raw not in candidates:
            candidates.append(raw)
    for pid in candidates:
        if is_process_running(pid):
            return pid
    return candidates[0] if candidates else None


def _spawn_node(args: list[str], env: dict[str, str] | None = None) -> int:
    root = whatsapp_root()
    index = root / "index.js"
    if not index.is_file():
        raise FileNotFoundError(f"WhatsApp validator not found at {index}")
    cmd = [settings.WHATSAPP_NODE_BIN, str(index), *args]
    proc = subprocess.Popen(
        cmd,
        cwd=str(root),
        env=_node_env(env),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return _detach_process(proc)


def start_pairing(account_name: str) -> int:
    name = validate_account_name(account_name)
    session_path = sessions_dir() / name
    session_path.mkdir(parents=True, exist_ok=True)
    old_pid = read_pairing_pid(name)
    terminate_process(old_pid)
    clear_pairing_pid(name)
    pairing_path = session_path / "pairing.json"
    if pairing_path.is_file():
        pairing_path.unlink()
    stderr_path = session_path / "pairing.stderr.log"
    stderr_path.unlink(missing_ok=True)
    root = whatsapp_root()
    index = root / "index.js"
    if not index.is_file():
        raise FileNotFoundError(f"WhatsApp validator not found at {index}")
    stderr_file = stderr_path.open("a", encoding="utf-8")
    proc = subprocess.Popen(
        [settings.WHATSAPP_NODE_BIN, str(index)],
        cwd=str(root),
        env=_node_env(
            {
                "PAIR_ONLY": "1",
                "PAIR_ACCOUNT": name,
            }
        ),
        stdout=subprocess.DEVNULL,
        stderr=stderr_file,
        start_new_session=True,
    )
    stderr_file.close()
    pid = _detach_process(proc)
    write_pairing_pid(name, pid)
    return pid


def _pid_cmdline(pid: int) -> str:
    proc_cmdline = Path(f"/proc/{pid}/cmdline")
    if proc_cmdline.is_file():
        try:
            parts = proc_cmdline.read_bytes().split(b"\x00")
            return " ".join(
                part.decode("utf-8", errors="replace")
                for part in parts
                if part
            ).strip()
        except OSError:
            pass
    return _pid_commandline(pid)


def _pid_commandline(pid: int) -> str:
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def _pid_environ_contains(pid: int, key: str, value: str) -> bool:
    needle = f"{key}={value}"
    proc_environ = Path(f"/proc/{pid}/environ")
    if proc_environ.is_file():
        try:
            blob = proc_environ.read_bytes()
        except OSError:
            return False
        return needle.encode() in blob
    try:
        result = subprocess.run(
            ["ps", "eww", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if result.returncode != 0:
        return False
    return needle in (result.stdout or "")


def _pid_belongs_to_check_job(pid: int, job_id: int) -> bool:
    """True if ``pid`` is still running the Node validator for this job's run dir."""
    run_dir = str(job_run_dir(job_id))
    root = str(whatsapp_root())
    cmd = _pid_cmdline(pid)
    if cmd and (
        run_dir in cmd
        or str(Path(root) / "index.js") in cmd
        or "index.js" in cmd
    ):
        return True
    if _pid_environ_contains(pid, "RUN_DIR", run_dir):
        return True
    return False


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


def is_process_running(pid: int | None, *, job_id: int | None = None) -> bool:
    if not pid:
        return False
    if _reap_child_exit_code(pid) is not None:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:
        if os.waitpid(pid, os.WNOHANG)[0] == 0:
            return True
    except ChildProcessError:
        pass
    if job_id is not None:
        return _pid_belongs_to_check_job(pid, job_id)
    return True


VALIDATOR_PID_FILENAME = "validator.pid"
# Max gap between progress.json writes before treating the job as idle (safe speed).
PROGRESS_ACTIVE_MAX_AGE_SECONDS = 300


def validator_pid_path(job_id: int) -> Path:
    return job_run_dir(job_id) / VALIDATOR_PID_FILENAME


def write_validator_pid(job_id: int, pid: int) -> None:
    run_path = job_run_dir(job_id)
    run_path.mkdir(parents=True, exist_ok=True)
    validator_pid_path(job_id).write_text(str(int(pid)), encoding="utf-8")


def read_validator_pid(job_id: int) -> int | None:
    path = validator_pid_path(job_id)
    if not path.is_file():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None


def clear_validator_pid(job_id: int) -> None:
    validator_pid_path(job_id).unlink(missing_ok=True)


def _coerce_child_pid(pid_or_proc) -> int:
    if hasattr(pid_or_proc, "pid"):
        return int(pid_or_proc.pid)
    return int(pid_or_proc)


def register_job_validator_pid(job, pid_or_proc) -> None:
    """Persist validator PID on the job and in the run directory."""
    pid = _coerce_child_pid(pid_or_proc)
    job.pid = pid
    write_validator_pid(job.id, pid)


def _find_validator_pid_by_run_dir(job_id: int) -> int | None:
    run_dir = str(job_run_dir(job_id))
    try:
        result = subprocess.run(
            ["pgrep", "-f", run_dir],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    for line in (result.stdout or "").strip().splitlines():
        try:
            pid = int(line.strip())
        except ValueError:
            continue
        if _pid_belongs_to_check_job(pid, job_id):
            return pid
    return None


def resolve_validator_pid(job) -> int | None:
    """Best-effort PID for the Node validator (DB, pid file, or process scan)."""
    candidates: list[int] = []
    if job.pid:
        candidates.append(int(job.pid))
    disk_pid = read_validator_pid(job.id)
    if disk_pid:
        candidates.append(disk_pid)
    found = _find_validator_pid_by_run_dir(job.id)
    if found:
        candidates.append(found)
    seen: set[int] = set()
    for pid in candidates:
        if pid in seen:
            continue
        seen.add(pid)
        if is_process_running(pid, job_id=job.id):
            return pid
    return None


def _progress_update_age_seconds(progress: dict[str, Any] | None) -> float | None:
    if not progress:
        return None
    raw = progress.get("timestamp")
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip().replace("Z", "+00:00")
    try:
        updated = datetime.fromisoformat(text)
    except ValueError:
        return None
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    return time.time() - updated.timestamp()


def is_progress_recently_active(
    job_id: int, *, max_age_seconds: int = PROGRESS_ACTIVE_MAX_AGE_SECONDS
) -> bool:
    """True when progress.json shows a recent, incomplete update (Node still working)."""
    progress = read_job_progress(job_id)
    if not progress:
        return False
    if is_progress_complete(progress):
        return False
    prog_status = _progress_terminal_status(progress)
    if prog_status in ("cancelled", "failed", "error"):
        return False
    age = _progress_update_age_seconds(progress)
    if age is None:
        path = job_run_dir(job_id) / "progress.json"
        try:
            age = time.time() - path.stat().st_mtime
        except OSError:
            return False
    return age <= max_age_seconds


def is_validator_running(job) -> bool:
    """True when the Node validator is still working on this job."""
    from tools.models import WhatsAppCheckJob

    if resolve_validator_pid(job) is not None:
        return True
    # Fresh progress alone must not resurrect a terminal job (e.g. after refresh).
    if job.status in (
        WhatsAppCheckJob.STATUS_RUNNING,
        WhatsAppCheckJob.STATUS_PENDING,
    ):
        return is_progress_recently_active(job.id)
    return False


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
) -> int:
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


def _processed_query_digits(job_id: int, default_cc: str = "") -> set[str]:
    """Query-digit keys for numbers already checked in this job's run dir."""
    done: set[str] = set()
    run_path = job_run_dir(job_id)
    for filename in (
        "verified_active_numbers.txt",
        "not_registered_numbers.txt",
    ):
        for line in _read_number_lines(run_path / filename):
            parsed = parse_number_line(line, default_cc)
            if parsed:
                done.add(parsed.query_digits)
    for line in _read_number_lines(run_path / "check_error_numbers.txt"):
        number, _ = parse_error_number_line(line)
        parsed = parse_number_line(number, default_cc)
        if parsed:
            done.add(parsed.query_digits)
    return done


def _previously_skipped_query_digits(job) -> set[str]:
    cc = job.local_trunk_country or ""
    skipped: set[str] = set()
    for line in job.previously_checked_numbers or []:
        parsed = parse_number_line(line, cc)
        if parsed:
            skipped.add(parsed.query_digits)
    return skipped


def remaining_numbers_for_job(job) -> list[str]:
    """Original input lines still to check (pending file first, else recompute)."""
    run_path = job_run_dir(job.id)
    cc = job.local_trunk_country or ""
    pending_path = run_path / "pending_numbers.txt"
    if pending_path.is_file():
        pending_lines = _read_number_lines(pending_path)
        if pending_lines:
            out: list[str] = []
            seen: set[str] = set()
            for line in pending_lines:
                parsed = parse_number_line(line, cc)
                key = parsed.query_digits if parsed else sanitize_number(line) or line
                if key in seen:
                    continue
                seen.add(key)
                out.append(line)
            return out

    skipped = _previously_skipped_query_digits(job)
    done = _processed_query_digits(job.id, cc)
    remaining: list[str] = []
    seen: set[str] = set()
    for line in parse_numbers_text(job.numbers_text):
        parsed = parse_number_line(line, cc)
        if not parsed:
            continue
        if parsed.query_digits in skipped or parsed.query_digits in done:
            continue
        if parsed.query_digits in seen:
            continue
        seen.add(parsed.query_digits)
        remaining.append(line)
    return remaining


def job_is_resumable(job) -> bool:
    """True when a stopped job still has numbers to check and no live validator."""
    from tools.models import WhatsAppCheckJob

    if resolve_validator_pid(job) is not None:
        return False
    if job.status == WhatsAppCheckJob.STATUS_PENDING:
        return False
    if job.status == WhatsAppCheckJob.STATUS_COMPLETED:
        progress = read_job_progress(job.id)
        if is_progress_complete(progress) and not remaining_numbers_for_job(job):
            return False

    if remaining_numbers_for_job(job):
        return True

    progress = read_job_progress(job.id)
    totals = _progress_totals(progress)
    total = int(totals.get("total") or 0)
    if not total:
        total = len(parse_numbers_text(job.numbers_text)) - len(
            job.previously_checked_numbers or []
        )
    checked = int(totals.get("checked") or job.checked_count or 0)
    pending = int(totals.get("pending") or 0)
    if pending > 0:
        return True
    if total > 0 and checked < total:
        return job.status in (
            WhatsAppCheckJob.STATUS_FAILED,
            WhatsAppCheckJob.STATUS_CANCELLED,
            WhatsAppCheckJob.STATUS_COMPLETED,
        )
    return False


def _mark_progress_not_done(job_id: int) -> None:
    path = job_run_dir(job_id) / "progress.json"
    if not path.is_file():
        return
    try:
        progress = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    if progress.get("done") is True:
        progress["done"] = False
        path.write_text(json.dumps(progress, indent=2), encoding="utf-8")


def resume_check_job(job) -> int:
    """Restart Node for an existing job, checking only remaining numbers."""
    remaining = remaining_numbers_for_job(job)
    if not remaining:
        raise ValueError("No numbers left to check for this job.")

    account_names = list(job.account_names or [])
    if not account_names:
        raise ValueError("This job has no WhatsApp accounts configured.")

    run_path = job_run_dir(job.id)
    run_path.mkdir(parents=True, exist_ok=True)
    numbers_file = run_path / "numbers.txt"
    numbers_file.write_text("\n".join(remaining) + "\n", encoding="utf-8")
    (run_path / "pending_numbers.txt").write_text(
        "\n".join(remaining) + "\n", encoding="utf-8"
    )
    _mark_progress_not_done(job.id)

    speed_key = job.speed if job.speed in ("safe", "normal", "fast") else "normal"
    env = {
        "NON_INTERACTIVE": "1",
        "RESUME_JOB": "1",
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
        "FETCH_PRESENCE": "1" if job.fetch_presence else "0",
    }
    cc = normalize_country_prefix(job.local_trunk_country or "")
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
    """True only when every input number was processed (checked >= total, no pending)."""
    if not progress:
        return False
    totals = _progress_totals(progress)
    total = int(totals.get("total") or 0)
    checked = int(totals.get("checked") or 0)
    pending = int(totals.get("pending") or 0)
    if pending > 0:
        return False
    if total > 0:
        return checked >= total
    return progress.get("done") is True


def _progress_terminal_status(progress: dict[str, Any] | None) -> str | None:
    if not progress:
        return None
    raw = progress.get("status")
    if not isinstance(raw, str) or not raw.strip():
        return None
    return raw.strip().lower()


def _progress_message(progress: dict[str, Any] | None) -> str:
    if not progress:
        return ""
    for key in ("message", "error", "reason"):
        val = progress.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _incomplete_progress_message(progress: dict[str, Any] | None, job) -> str:
    totals = _progress_totals(progress)
    total = int(totals.get("total") or 0) or len(parse_numbers_text(job.numbers_text))
    checked = int(totals.get("checked") or 0)
    cc = job.local_trunk_country or ""
    checked = max(checked, len(_processed_query_digits(job.id, cc)))
    if total:
        return (
            f"Check stopped before finishing "
            f"({checked:,} of {total:,} numbers processed)."
        )
    return "Check stopped before completion."


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

    checked_count = int(checked or 0)
    pending_count = int(totals.get("pending") or 0) if totals else 0
    if not pending_count and total_count:
        pending_count = max(0, total_count - checked_count - skipped_count)

    return {
        "total_count": total_count,
        "checked_count": checked_count,
        "pending_count": pending_count,
        "valid_count": valid_count,
        "invalid_count": invalid_count,
        "error_count": error_count,
        "skipped_count": skipped_count,
        "valid_numbers": valid_numbers,
        "error_numbers": error_numbers,
        "previously_checked_numbers": previously_checked,
        "is_running": is_validator_running(job),
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
    running = is_validator_running(job)

    if (
        job.status == WhatsAppCheckJob.STATUS_COMPLETED
        and not running
        and progress
        and not complete
    ):
        job.status = WhatsAppCheckJob.STATUS_FAILED
        job.error_message = (
            job.error_message or _incomplete_progress_message(progress, job)
        )
        job.pid = None
        clear_validator_pid(job.id)
        job.finished_at = job.finished_at or datetime.now(timezone.utc)
        return

    if running and not complete:
        pid = resolve_validator_pid(job)
        if not pid:
            return
        register_job_validator_pid(job, pid)
        reconnected = job.status == WhatsAppCheckJob.STATUS_FAILED
        if job.status in (
            WhatsAppCheckJob.STATUS_RUNNING,
            WhatsAppCheckJob.STATUS_PENDING,
        ) or reconnected:
            job.status = WhatsAppCheckJob.STATUS_RUNNING
            job.error_message = ""
            if reconnected:
                job.finished_at = None
        return

    if job.status not in (
        WhatsAppCheckJob.STATUS_RUNNING,
        WhatsAppCheckJob.STATUS_PENDING,
    ):
        return

    now = datetime.now(timezone.utc)
    if complete:
        was_completed = job.status == WhatsAppCheckJob.STATUS_COMPLETED
        job.status = WhatsAppCheckJob.STATUS_COMPLETED
        job.finished_at = job.finished_at or now
        job.pid = None
        clear_validator_pid(job.id)
        if not was_completed:
            record_verified_from_job(job)
        return

    had_pid = bool(job.pid) or read_validator_pid(job.id) is not None
    job.pid = None
    clear_validator_pid(job.id)
    job.finished_at = job.finished_at or now
    prog_status = _progress_terminal_status(progress)

    if prog_status == "cancelled":
        job.status = WhatsAppCheckJob.STATUS_CANCELLED
        job.error_message = _progress_message(progress) or "Check was cancelled."
    elif prog_status in ("failed", "error"):
        job.status = WhatsAppCheckJob.STATUS_FAILED
        job.error_message = _progress_message(progress) or "Check failed."
    elif progress:
        job.status = WhatsAppCheckJob.STATUS_FAILED
        job.error_message = (
            job.error_message or _incomplete_progress_message(progress, job)
        )
    elif had_pid:
        job.status = WhatsAppCheckJob.STATUS_FAILED
        job.error_message = (
            job.error_message or "Validator process exited unexpectedly."
        )
    else:
        job.status = WhatsAppCheckJob.STATUS_FAILED
        job.error_message = (
            job.error_message or "Check did not produce progress output."
        )
