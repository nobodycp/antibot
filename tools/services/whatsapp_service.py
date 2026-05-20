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
from typing import Any, Literal

AccountStatus = Literal["online", "offline", "pairing", "unknown"]

from django.conf import settings

_ACCOUNT_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


@dataclass
class WhatsAppAccountInfo:
    name: str
    has_session: bool
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


def read_live_numbers(job_id: int) -> list[str]:
    return _read_number_lines(job_run_dir(job_id) / "verified_active_numbers.txt")


def read_error_numbers(job_id: int) -> list[str]:
    return _read_number_lines(job_run_dir(job_id) / "check_error_numbers.txt")


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

    total_count = totals.get("total") or len(parse_numbers_text(job.numbers_text))
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

    return {
        "total_count": total_count,
        "valid_count": valid_count,
        "invalid_count": invalid_count,
        "error_count": error_count,
        "valid_numbers": valid_numbers,
        "error_numbers": error_numbers,
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
        job.status = WhatsAppCheckJob.STATUS_COMPLETED
        job.finished_at = job.finished_at or now
        job.pid = None
    elif job.pid:
        job.status = WhatsAppCheckJob.STATUS_FAILED
        job.error_message = job.error_message or "Validator process exited unexpectedly."
        job.finished_at = job.finished_at or now
        job.pid = None
