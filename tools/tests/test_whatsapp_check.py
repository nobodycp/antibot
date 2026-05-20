import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from tools.models import WhatsAppAccount, WhatsAppCheckJob, WhatsAppVerifiedNumber
from tools.services import whatsapp_accounts as wa_accounts
from tools.services import whatsapp_service as wa

User = get_user_model()


class WhatsAppCheckPermissionTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=False)
        self.user = User.objects.create_user(username="regular", password="pass")
        self.superuser = User.objects.create_superuser(
            username="super_u",
            password="pass-s",
            email="super@example.com",
        )

    def test_anonymous_redirected(self):
        r = self.client.get(reverse("tools:whatsapp_check"))
        self.assertEqual(r.status_code, 302)

    def test_regular_user_forbidden(self):
        self.client.force_login(self.user)
        r = self.client.get(reverse("tools:whatsapp_check"))
        self.assertEqual(r.status_code, 302)

    def test_superuser_can_open_page(self):
        self.client.force_login(self.superuser)
        r = self.client.get(reverse("tools:whatsapp_check"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "WhatsApp Check")


class WhatsAppServiceTests(TestCase):
    def test_parse_numbers_dedupes(self):
        text = "966501234567\n966501234567\n# comment\n\n972:0531234567"
        lines = wa.parse_numbers_text(text)
        self.assertEqual(len(lines), 2)

    def test_validate_account_name_rejects_invalid(self):
        with self.assertRaises(ValueError):
            wa.validate_account_name("../evil")

    def test_suggest_next_account_name(self):
        name = wa.suggest_next_account_name()
        self.assertTrue(name.startswith("acc_"))

    def test_normalize_country_prefix(self):
        self.assertEqual(wa.normalize_country_prefix(""), "")
        self.assertEqual(wa.normalize_country_prefix("  "), "")
        self.assertEqual(wa.normalize_country_prefix("972"), "972")
        self.assertEqual(wa.normalize_country_prefix("972:"), "972")
        self.assertEqual(wa.normalize_country_prefix(" 972: "), "972")

    def test_parse_number_line_trunk_prefix(self):
        parsed = wa.parse_number_line("0512345678", "972")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.query_digits, "972512345678")
        self.assertEqual(parsed.file_digits, "0512345678")

    def test_parse_number_line_per_line_country(self):
        parsed = wa.parse_number_line("972:0531234567", "")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.query_digits, "972531234567")

    def test_split_numbers_by_verified_history(self):
        WhatsAppVerifiedNumber.objects.create(phone="966501234567")
        split = wa.split_numbers_by_verified_history(
            ["966501234567", "966509876543"], "966"
        )
        self.assertEqual(split.already_verified, ["966501234567"])
        self.assertEqual(split.to_check, ["966509876543"])

    def test_record_verified_from_job(self):
        user = User.objects.create_superuser(
            username="rec_u", password="x", email="rec@e.com"
        )
        job = WhatsAppCheckJob.objects.create(
            user=user,
            numbers_text="966501234567",
            status=WhatsAppCheckJob.STATUS_COMPLETED,
        )
        run_path = wa.job_run_dir(job.id)
        run_path.mkdir(parents=True, exist_ok=True)
        (run_path / "verified_active_numbers.txt").write_text(
            "966501234567\n", encoding="utf-8"
        )
        count = wa.record_verified_from_job(job)
        self.assertEqual(count, 1)
        self.assertTrue(
            WhatsAppVerifiedNumber.objects.filter(phone="966501234567").exists()
        )

    def test_sync_job_records_verified_on_complete(self):
        user = User.objects.create_superuser(
            username="sync_rec_u", password="x", email="syncrec@e.com"
        )
        job = WhatsAppCheckJob.objects.create(
            user=user,
            numbers_text="966501234567",
            status=WhatsAppCheckJob.STATUS_RUNNING,
            pid=999999,
        )
        run_path = wa.job_run_dir(job.id)
        run_path.mkdir(parents=True, exist_ok=True)
        (run_path / "progress.json").write_text(
            json.dumps({"done": True, "totals": {"total": 1, "checked": 1, "live": 1}}),
            encoding="utf-8",
        )
        (run_path / "verified_active_numbers.txt").write_text(
            "966501234567\n", encoding="utf-8"
        )
        with patch.object(wa, "is_process_running", return_value=False):
            wa.sync_job_from_disk(job)
        self.assertEqual(job.status, WhatsAppCheckJob.STATUS_COMPLETED)
        self.assertTrue(
            WhatsAppVerifiedNumber.objects.filter(phone="966501234567").exists()
        )

    def test_jid_to_phone_parses_baileys_me_id(self):
        self.assertEqual(
            wa._jid_to_phone("972595108208:1@s.whatsapp.net"), "972595108208"
        )
        self.assertIsNone(wa._jid_to_phone("not-a-jid"))
        self.assertIsNone(wa._jid_to_phone(None))

    def test_get_account_phone_from_creds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = root / "sessions" / "acc_1"
            session.mkdir(parents=True)
            (session / "creds.json").write_text(
                json.dumps({"me": {"id": "966501234567:1@s.whatsapp.net"}}),
                encoding="utf-8",
            )
            with override_settings(WHATSAPP_ROOT=root):
                self.assertEqual(wa.get_account_phone("acc_1"), "966501234567")

    def test_get_account_phone_from_connection_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = root / "sessions" / "acc_1"
            session.mkdir(parents=True)
            (session / "connection_status.json").write_text(
                json.dumps({"phone": "972501234567", "jid": "972501234567:1@s.whatsapp.net"}),
                encoding="utf-8",
            )
            with override_settings(WHATSAPP_ROOT=root):
                self.assertEqual(wa.get_account_phone("acc_1"), "972501234567")

    def test_list_accounts_includes_phone(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = root / "sessions" / "acc_1"
            session.mkdir(parents=True)
            (session / "creds.json").write_text(
                json.dumps({"me": {"id": "966501234567:1@s.whatsapp.net"}}),
                encoding="utf-8",
            )
            with override_settings(WHATSAPP_ROOT=root):
                accounts = wa.list_accounts()
            self.assertEqual(len(accounts), 1)
            self.assertEqual(accounts[0].phone, "966501234567")

    def test_is_process_running_false_after_child_exits(self):
        proc = subprocess.Popen(
            [sys.executable, "-c", "pass"],
            start_new_session=True,
        )
        pid = proc.pid
        proc.wait()
        self.assertFalse(wa.is_process_running(pid))

    def test_is_process_running_false_when_pid_not_validator(self):
        """PID reuse: another process holds the pid; not our Node validator."""
        with patch.object(os, "waitpid", side_effect=ChildProcessError()):
            with patch.object(wa, "_pid_belongs_to_check_job", return_value=False):
                self.assertFalse(wa.is_process_running(os.getpid(), job_id=1))

    def test_status_label_for_invalid_status_value(self):
        user = User.objects.create_superuser(
            username="lbl_u", password="x", email="lbl@e.com"
        )
        job = WhatsAppCheckJob.objects.create(
            user=user,
            numbers_text="966501234567",
            status="mystery",
        )
        self.assertEqual(job.status_label, "Mystery")

    def test_sync_job_marks_failed_when_process_dead_incomplete(self):
        user = User.objects.create_superuser(
            username="sync_fail_u", password="x", email="syncfail@e.com"
        )
        job = WhatsAppCheckJob.objects.create(
            user=user,
            numbers_text="966501234567",
            status=WhatsAppCheckJob.STATUS_RUNNING,
            pid=999999,
        )
        run_path = wa.job_run_dir(job.id)
        run_path.mkdir(parents=True, exist_ok=True)
        (run_path / "progress.json").write_text(
            json.dumps(
                {
                    "done": False,
                    "totals": {
                        "total": 2000,
                        "checked": 43,
                        "live": 4,
                        "errors": 0,
                        "invalid": 39,
                    },
                    "results": [],
                }
            ),
            encoding="utf-8",
        )
        with patch.object(wa, "is_process_running", return_value=False):
            wa.sync_job_from_disk(job)
        self.assertEqual(job.status, WhatsAppCheckJob.STATUS_FAILED)
        self.assertIn("stopped before finishing", job.error_message)
        self.assertIsNone(job.pid)
        self.assertIsNotNone(job.finished_at)
        self.assertTrue(wa.job_is_resumable(job))

    def test_job_is_resumable_when_pending_numbers_exist(self):
        user = User.objects.create_superuser(
            username="pend_u", password="x", email="pend@e.com"
        )
        job = WhatsAppCheckJob.objects.create(
            user=user,
            numbers_text="966501234567\n966509876543",
            status=WhatsAppCheckJob.STATUS_CANCELLED,
            account_names=["acc_1"],
        )
        run_path = wa.job_run_dir(job.id)
        run_path.mkdir(parents=True, exist_ok=True)
        (run_path / "pending_numbers.txt").write_text(
            "966509876543\n", encoding="utf-8"
        )
        self.assertTrue(wa.job_is_resumable(job))
        self.assertEqual(
            wa.remaining_numbers_for_job(job), ["966509876543"]
        )

    def test_remaining_numbers_recomputed_from_outputs(self):
        user = User.objects.create_superuser(
            username="recomp_u", password="x", email="recomp@e.com"
        )
        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(WHATSAPP_ROOT=Path(tmp)):
                job = WhatsAppCheckJob.objects.create(
                    user=user,
                    numbers_text="966501234567\n966509876543\n966501111111",
                    status=WhatsAppCheckJob.STATUS_FAILED,
                    account_names=["acc_1"],
                )
                run_path = wa.job_run_dir(job.id)
                run_path.mkdir(parents=True, exist_ok=True)
                (run_path / "verified_active_numbers.txt").write_text(
                    "966501234567\n", encoding="utf-8"
                )
                remaining = wa.remaining_numbers_for_job(job)
        self.assertEqual(
            set(remaining), {"966509876543", "966501111111"}
        )

    def test_job_not_resumable_when_completed(self):
        user = User.objects.create_superuser(
            username="done_u", password="x", email="done@e.com"
        )
        job = WhatsAppCheckJob.objects.create(
            user=user,
            numbers_text="966501234567",
            status=WhatsAppCheckJob.STATUS_COMPLETED,
            account_names=["acc_1"],
        )
        run_path = wa.job_run_dir(job.id)
        run_path.mkdir(parents=True, exist_ok=True)
        (run_path / "verified_active_numbers.txt").write_text(
            "966501234567\n", encoding="utf-8"
        )
        self.assertFalse(wa.job_is_resumable(job))

    def test_parse_error_number_line_with_reason(self):
        number, reason = wa.parse_error_number_line("972555544071 --> offline account")
        self.assertEqual(number, "972555544071")
        self.assertEqual(reason, "offline account")

    def test_parse_error_number_line_legacy_number_only(self):
        number, reason = wa.parse_error_number_line("966501234567")
        self.assertEqual(number, "966501234567")
        self.assertEqual(reason, "")

    def test_read_error_numbers_formats_display_lines(self):
        user = User.objects.create_superuser(
            username="err_u", password="x", email="err@e.com"
        )
        job = WhatsAppCheckJob.objects.create(
            user=user,
            numbers_text="972555544071",
            status=WhatsAppCheckJob.STATUS_RUNNING,
        )
        run_path = wa.job_run_dir(job.id)
        run_path.mkdir(parents=True, exist_ok=True)
        (run_path / "check_error_numbers.txt").write_text(
            "972555544071 --> offline account\n966501234567 --> rate limited\n",
            encoding="utf-8",
        )
        lines = wa.read_error_numbers(job.id)
        self.assertEqual(
            lines,
            [
                "972555544071 --> offline account",
                "966501234567 --> rate limited",
            ],
        )

    def test_build_job_snapshot_includes_error_lines_with_reasons(self):
        job = WhatsAppCheckJob.objects.create(
            user=User.objects.create_superuser(
                username="snap_err_u", password="x", email="se@e.com"
            ),
            numbers_text="972555544071",
            status=WhatsAppCheckJob.STATUS_COMPLETED,
        )
        run_path = wa.job_run_dir(job.id)
        run_path.mkdir(parents=True, exist_ok=True)
        (run_path / "check_error_numbers.txt").write_text(
            "972555544071 --> offline account\n", encoding="utf-8"
        )
        (run_path / "progress.json").write_text(
            json.dumps(
                {
                    "done": True,
                    "totals": {
                        "total": 1,
                        "checked": 1,
                        "live": 0,
                        "errors": 1,
                        "invalid": 0,
                    },
                    "results": [],
                }
            ),
            encoding="utf-8",
        )
        snap = wa.build_job_snapshot(job)
        self.assertEqual(snap["error_numbers"], ["972555544071 --> offline account"])
        self.assertEqual(snap["error_count"], 1)

    def test_is_progress_complete(self):
        self.assertFalse(wa.is_progress_complete(None))
        self.assertTrue(
            wa.is_progress_complete(
                {"done": True, "totals": {"total": 1, "checked": 0}}
            )
        )
        self.assertTrue(
            wa.is_progress_complete(
                {"totals": {"total": 2, "checked": 2, "live": 1, "errors": 0}}
            )
        )
        self.assertFalse(
            wa.is_progress_complete(
                {"totals": {"total": 2, "checked": 1, "live": 0, "errors": 0}}
            )
        )

    def test_sync_job_marks_completed_when_progress_done(self):
        user = User.objects.create_superuser(
            username="sync_u", password="x", email="sync@e.com"
        )
        job = WhatsAppCheckJob.objects.create(
            user=user,
            numbers_text="966501234567",
            status=WhatsAppCheckJob.STATUS_RUNNING,
            pid=999999,
        )
        run_path = wa.job_run_dir(job.id)
        run_path.mkdir(parents=True, exist_ok=True)
        (run_path / "progress.json").write_text(
            json.dumps(
                {
                    "done": True,
                    "totals": {
                        "total": 1,
                        "checked": 1,
                        "live": 1,
                        "errors": 0,
                        "invalid": 0,
                    },
                    "results": [],
                }
            ),
            encoding="utf-8",
        )
        with patch.object(wa, "is_process_running", return_value=True):
            wa.sync_job_from_disk(job)
        self.assertEqual(job.status, WhatsAppCheckJob.STATUS_COMPLETED)
        self.assertIsNone(job.pid)
        self.assertIsNotNone(job.finished_at)

    def test_sync_job_marks_completed_when_process_exited(self):
        user = User.objects.create_superuser(
            username="sync_u2", password="x", email="sync2@e.com"
        )
        proc = subprocess.Popen(
            [sys.executable, "-c", "pass"],
            start_new_session=True,
        )
        proc.wait()
        job = WhatsAppCheckJob.objects.create(
            user=user,
            numbers_text="966501234567",
            status=WhatsAppCheckJob.STATUS_RUNNING,
            pid=proc.pid,
        )
        run_path = wa.job_run_dir(job.id)
        run_path.mkdir(parents=True, exist_ok=True)
        (run_path / "progress.json").write_text(
            json.dumps(
                {
                    "totals": {
                        "total": 1,
                        "checked": 1,
                        "live": 0,
                        "errors": 0,
                        "invalid": 1,
                    },
                    "results": [],
                }
            ),
            encoding="utf-8",
        )
        wa.sync_job_from_disk(job)
        self.assertEqual(job.status, WhatsAppCheckJob.STATUS_COMPLETED)
        self.assertIsNone(job.pid)

    def test_build_job_snapshot_from_progress(self):
        from tools.models import WhatsAppCheckJob

        job = WhatsAppCheckJob.objects.create(
            user=User.objects.create_superuser(
                username="snap_u", password="x", email="s@e.com"
            ),
            numbers_text="966501234567\n966509876543",
            status=WhatsAppCheckJob.STATUS_RUNNING,
        )
        run_path = wa.job_run_dir(job.id)
        run_path.mkdir(parents=True, exist_ok=True)
        (run_path / "progress.json").write_text(
            json.dumps(
                {
                    "totals": {
                        "total": 2,
                        "checked": 2,
                        "live": 1,
                        "errors": 0,
                        "invalid": 1,
                    },
                    "results": [],
                }
            ),
            encoding="utf-8",
        )
        (run_path / "verified_active_numbers.txt").write_text(
            "966501234567\n", encoding="utf-8"
        )
        snap = wa.build_job_snapshot(job)
        self.assertEqual(snap["total_count"], 2)
        self.assertEqual(snap["valid_count"], 1)
        self.assertEqual(snap["invalid_count"], 1)
        self.assertEqual(snap["valid_numbers"], ["966501234567"])

    @patch("tools.services.whatsapp_service._spawn_node")
    def test_start_check_job_sets_trunk_env(self, mock_spawn):
        mock_spawn.return_value = MagicMock(pid=1)
        wa.start_check_job(
            job_id=99,
            numbers=["0512345678"],
            account_names=["acc_1"],
            speed="normal",
            fetch_presence=False,
            local_trunk_country="972:",
        )
        env = mock_spawn.call_args[0][1]
        self.assertEqual(env["LOCAL_TRUNK_COUNTRY"], "972")

    @patch("tools.services.whatsapp_service._spawn_node")
    def test_start_check_job_omits_trunk_env_when_empty(self, mock_spawn):
        mock_spawn.return_value = MagicMock(pid=1)
        wa.start_check_job(
            job_id=100,
            numbers=["966501234567"],
            account_names=["acc_1"],
            speed="normal",
            fetch_presence=False,
            local_trunk_country="",
        )
        env = mock_spawn.call_args[0][1]
        self.assertNotIn("LOCAL_TRUNK_COUNTRY", env)

    def test_get_account_status_offline_without_creds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sessions" / "acc_1").mkdir(parents=True)
            with override_settings(WHATSAPP_ROOT=root):
                self.assertEqual(
                    wa.get_account_status("acc_1", probe_if_stale=False), "offline"
                )

    def test_get_pairing_status_error_when_pair_process_exited(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = root / "sessions" / "acc_1"
            session.mkdir(parents=True)
            (session / "pairing.stderr.log").write_text(
                "Error: Cannot find module 'qrcode'", encoding="utf-8"
            )
            with override_settings(WHATSAPP_ROOT=root):
                status = wa.get_pairing_status("acc_1", pair_pid=999999)
                self.assertEqual(status["status"], "error")
                self.assertIn("qrcode", status["message"])

    def test_get_pairing_status_idle_shows_connecting_while_pairing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sessions" / "acc_1").mkdir(parents=True)
            with override_settings(WHATSAPP_ROOT=root):
                status = wa.get_pairing_status("acc_1")
                self.assertEqual(status["status"], "connecting")

    def test_get_account_status_pairing_from_pairing_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = root / "sessions" / "acc_1"
            session.mkdir(parents=True)
            (session / "creds.json").write_text("{}", encoding="utf-8")
            (session / "pairing.json").write_text(
                json.dumps({"status": "qr", "message": "Scan QR"}),
                encoding="utf-8",
            )
            with override_settings(WHATSAPP_ROOT=root):
                self.assertEqual(
                    wa.get_account_status("acc_1", probe_if_stale=False), "pairing"
                )

    def test_get_account_status_reads_connection_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = root / "sessions" / "acc_1"
            session.mkdir(parents=True)
            (session / "creds.json").write_text("{}", encoding="utf-8")
            (session / "connection_status.json").write_text(
                json.dumps(
                    {
                        "status": "online",
                        "message": "Connected",
                        "updated_at": "2099-01-01T00:00:00+00:00",
                    }
                ),
                encoding="utf-8",
            )
            with override_settings(WHATSAPP_ROOT=root):
                self.assertEqual(
                    wa.get_account_status("acc_1", probe_if_stale=False), "online"
                )

    @patch("tools.services.whatsapp_service._run_status_probe", return_value=True)
    def test_refresh_accounts_connection_status_probes_stale(self, mock_probe):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sessions" / "acc_1").mkdir(parents=True)
            (root / "sessions" / "acc_1" / "creds.json").write_text("{}", encoding="utf-8")
            with override_settings(WHATSAPP_ROOT=root):
                wa.refresh_accounts_connection_status(["acc_1"], max_age_seconds=30)
            mock_probe.assert_called_once_with(["acc_1"])


class WhatsAppAccountsStatusTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=False)
        self.superuser = User.objects.create_superuser(
            username="wa_status_u",
            password="pass-s",
            email="status@example.com",
        )
        self.client.force_login(self.superuser)

    def test_accounts_status_partial_requires_superuser(self):
        user = User.objects.create_user(username="reg", password="x")
        anon_client = Client(enforce_csrf_checks=False)
        r = anon_client.get(reverse("tools:whatsapp_accounts_status"))
        self.assertEqual(r.status_code, 302)
        reg_client = Client(enforce_csrf_checks=False)
        reg_client.force_login(user)
        r = reg_client.get(reverse("tools:whatsapp_accounts_status"))
        self.assertEqual(r.status_code, 302)

    @patch("tools.views.whatsapp_views.wa.refresh_accounts_connection_status")
    @patch("tools.views.whatsapp_views.wa.get_account_status", return_value="online")
    @patch("tools.services.whatsapp_accounts.wa.list_accounts")
    def test_accounts_status_partial_renders_online(
        self, mock_list, mock_status, mock_refresh
    ):
        mock_list.return_value = [
            wa.WhatsAppAccountInfo(
                name="acc_1",
                has_session=True,
                phone="966501234567",
                pairing_status=None,
                pairing_message=None,
                qr_data_url=None,
            )
        ]
        r = self.client.get(
            reverse("tools:whatsapp_accounts_status"),
            {"seconds": "45"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Online")
        self.assertContains(r, "acc_1")
        self.assertContains(r, "966501234567")
        mock_refresh.assert_called_once()
        self.assertEqual(mock_refresh.call_args.kwargs["max_age_seconds"], 45)

    def test_accounts_tab_shows_interval_input(self):
        r = self.client.get(reverse("tools:whatsapp_check"), {"tab": "accounts"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Status check interval (seconds)")
        self.assertContains(r, 'name="seconds"')
        self.assertContains(r, ">Phone<")
        self.assertContains(r, ">Owner<")

    def test_accounts_tab_shows_em_dash_without_phone(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sessions" / "acc_1").mkdir(parents=True)
            with override_settings(WHATSAPP_ROOT=root):
                r = self.client.get(
                    reverse("tools:whatsapp_check"), {"tab": "accounts"}
                )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "—")


class WhatsAppCheckJobTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=False)
        self.superuser = User.objects.create_superuser(
            username="super_u",
            password="pass-s",
            email="super@example.com",
        )
        self.client.force_login(self.superuser)

    @patch("tools.views.whatsapp_views.wa.start_check_job")
    @patch("tools.views.whatsapp_views._linked_account_names", return_value=["acc_1"])
    def test_start_check_creates_job(self, _linked, mock_start):
        mock_start.return_value = MagicMock(pid=4242)
        r = self.client.post(
            reverse("tools:whatsapp_check"),
            {
                "action": "start_check",
                "numbers": "966501234567",
                "speed": "normal",
            },
        )
        self.assertEqual(r.status_code, 302)
        job = WhatsAppCheckJob.objects.get()
        self.assertEqual(job.status, WhatsAppCheckJob.STATUS_RUNNING)
        self.assertEqual(job.pid, 4242)
        mock_start.assert_called_once()
        kwargs = mock_start.call_args.kwargs
        self.assertEqual(kwargs.get("local_trunk_country"), "")

    @patch("tools.views.whatsapp_views.wa.start_check_job")
    @patch("tools.views.whatsapp_views._linked_account_names", return_value=["acc_1"])
    def test_start_check_skips_previously_verified(self, _linked, mock_start):
        WhatsAppVerifiedNumber.objects.create(phone="966501234567")
        mock_start.return_value = MagicMock(pid=4242)
        self.client.post(
            reverse("tools:whatsapp_check"),
            {
                "action": "start_check",
                "numbers": "966501234567\n966509876543",
                "speed": "normal",
            },
        )
        job = WhatsAppCheckJob.objects.get()
        self.assertEqual(job.previously_checked_numbers, ["966501234567"])
        mock_start.assert_called_once()
        self.assertEqual(
            mock_start.call_args.kwargs["numbers"], ["966509876543"]
        )

    @patch("tools.views.whatsapp_views.wa.start_check_job")
    @patch("tools.views.whatsapp_views._linked_account_names", return_value=["acc_1"])
    def test_start_check_all_verified_completes_without_node(self, _linked, mock_start):
        WhatsAppVerifiedNumber.objects.create(phone="966501234567")
        self.client.post(
            reverse("tools:whatsapp_check"),
            {
                "action": "start_check",
                "numbers": "966501234567",
                "speed": "normal",
            },
        )
        job = WhatsAppCheckJob.objects.get()
        self.assertEqual(job.status, WhatsAppCheckJob.STATUS_COMPLETED)
        mock_start.assert_not_called()
        self.assertEqual(job.previously_checked_numbers, ["966501234567"])

    @patch("tools.views.whatsapp_views.wa.start_check_job")
    @patch("tools.views.whatsapp_views._linked_account_names", return_value=["acc_1"])
    def test_start_check_passes_country_prefix(self, _linked, mock_start):
        mock_start.return_value = MagicMock(pid=4242)
        self.client.post(
            reverse("tools:whatsapp_check"),
            {
                "action": "start_check",
                "numbers": "0512345678",
                "country_prefix": "972:",
                "speed": "normal",
            },
        )
        job = WhatsAppCheckJob.objects.get()
        self.assertEqual(job.local_trunk_country, "972")
        mock_start.assert_called_once()
        self.assertEqual(
            mock_start.call_args.kwargs.get("local_trunk_country"), "972"
        )

    @patch("tools.views.whatsapp_views.wa.start_check_job")
    @patch("tools.views.whatsapp_views._linked_account_names", return_value=["acc_1"])
    def test_page_reconciles_stuck_running_job(self, _linked, mock_start):
        mock_start.return_value = MagicMock(pid=4242)
        proc = subprocess.Popen(
            [sys.executable, "-c", "pass"],
            start_new_session=True,
        )
        proc.wait()
        job = WhatsAppCheckJob.objects.create(
            user=self.superuser,
            numbers_text="966501234567",
            status=WhatsAppCheckJob.STATUS_RUNNING,
            pid=proc.pid,
        )
        run_path = wa.job_run_dir(job.id)
        run_path.mkdir(parents=True, exist_ok=True)
        (run_path / "progress.json").write_text(
            json.dumps(
                {
                    "done": True,
                    "totals": {
                        "total": 1,
                        "checked": 1,
                        "live": 1,
                        "errors": 0,
                        "invalid": 0,
                    },
                    "results": [],
                }
            ),
            encoding="utf-8",
        )
        r = self.client.get(reverse("tools:whatsapp_check"))
        self.assertEqual(r.status_code, 200)
        job.refresh_from_db()
        self.assertEqual(job.status, WhatsAppCheckJob.STATUS_COMPLETED)
        self.assertNotContains(r, "A job is already running")

    def test_results_panel_shows_previously_checked_section(self):
        job = WhatsAppCheckJob.objects.create(
            user=self.superuser,
            numbers_text="966501234567\n966509876543",
            status=WhatsAppCheckJob.STATUS_COMPLETED,
            previously_checked_numbers=["966501234567"],
        )
        r = self.client.get(
            reverse("tools:whatsapp_check"), {"tab": "check", "job": job.id}
        )
        self.assertContains(r, "Previously checked")
        self.assertContains(r, "Previously")
        self.assertContains(r, "966501234567")

    def test_status_partial_triggers_recent_jobs_refresh(self):
        job = WhatsAppCheckJob.objects.create(
            user=self.superuser,
            numbers_text="966501234567",
            status=WhatsAppCheckJob.STATUS_RUNNING,
        )
        r = self.client.get(reverse("tools:whatsapp_check_status", args=[job.id]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["HX-Trigger"], "waRecentJobsRefresh")

    @patch("tools.views.whatsapp_views.wa.resume_check_job")
    def test_continue_job_restarts_validator(self, mock_resume):
        mock_resume.return_value = MagicMock(pid=5151)
        job = WhatsAppCheckJob.objects.create(
            user=self.superuser,
            numbers_text="966501234567\n966509876543",
            status=WhatsAppCheckJob.STATUS_FAILED,
            account_names=["acc_1"],
            error_message="Check stopped before finishing (1 of 2 numbers processed).",
        )
        run_path = wa.job_run_dir(job.id)
        run_path.mkdir(parents=True, exist_ok=True)
        (run_path / "pending_numbers.txt").write_text(
            "966509876543\n", encoding="utf-8"
        )
        r = self.client.post(
            reverse("tools:whatsapp_check_continue", args=[job.id])
        )
        self.assertEqual(r.status_code, 302)
        job.refresh_from_db()
        self.assertEqual(job.status, WhatsAppCheckJob.STATUS_RUNNING)
        self.assertEqual(job.pid, 5151)
        self.assertEqual(job.error_message, "")
        mock_resume.assert_called_once()

    def test_view_shows_continue_for_failed_partial_job(self):
        job = WhatsAppCheckJob.objects.create(
            user=self.superuser,
            numbers_text="966501234567\n966509876543",
            status=WhatsAppCheckJob.STATUS_FAILED,
            account_names=["acc_1"],
            error_message="Check stopped before finishing (1 of 2 numbers processed).",
        )
        run_path = wa.job_run_dir(job.id)
        run_path.mkdir(parents=True, exist_ok=True)
        (run_path / "verified_active_numbers.txt").write_text(
            "966501234567\n", encoding="utf-8"
        )
        (run_path / "progress.json").write_text(
            json.dumps(
                {
                    "done": False,
                    "totals": {
                        "total": 2,
                        "checked": 1,
                        "live": 1,
                        "errors": 0,
                        "invalid": 0,
                    },
                    "results": [],
                }
            ),
            encoding="utf-8",
        )
        r = self.client.get(
            reverse("tools:whatsapp_check"), {"tab": "check", "job": job.id}
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Continue")
        self.assertContains(
            r, reverse("tools:whatsapp_check_continue", args=[job.id])
        )
        self.assertContains(r, ">Continue</button>")

    def test_cancelled_job_shows_continue_in_recent_jobs(self):
        job = WhatsAppCheckJob.objects.create(
            user=self.superuser,
            numbers_text="966501234567\n966509876543",
            status=WhatsAppCheckJob.STATUS_CANCELLED,
            account_names=["acc_1"],
        )
        run_path = wa.job_run_dir(job.id)
        run_path.mkdir(parents=True, exist_ok=True)
        (run_path / "pending_numbers.txt").write_text(
            "966509876543\n", encoding="utf-8"
        )
        r = self.client.get(reverse("tools:whatsapp_check_recent_jobs"))
        self.assertContains(r, "Continue")
        self.assertContains(r, f"whatsapp-check/jobs/{job.id}/continue/")

    def test_recent_jobs_partial_shows_terminal_status_badges(self):
        WhatsAppCheckJob.objects.create(
            user=self.superuser,
            numbers_text="966501234567",
            status=WhatsAppCheckJob.STATUS_COMPLETED,
        )
        WhatsAppCheckJob.objects.create(
            user=self.superuser,
            numbers_text="966509876543",
            status=WhatsAppCheckJob.STATUS_CANCELLED,
        )
        WhatsAppCheckJob.objects.create(
            user=self.superuser,
            numbers_text="966501111111",
            status=WhatsAppCheckJob.STATUS_FAILED,
        )
        r = self.client.get(reverse("tools:whatsapp_check_recent_jobs"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'class="ds-text-success"')
        self.assertContains(r, "Completed")
        self.assertContains(r, 'class="ds-text-danger"')
        self.assertContains(r, "Cancelled")
        self.assertContains(r, "Failed")

    def test_status_partial_syncs_job_and_recent_jobs_reflects_completion(self):
        proc = subprocess.Popen(
            [sys.executable, "-c", "pass"],
            start_new_session=True,
        )
        proc.wait()
        job = WhatsAppCheckJob.objects.create(
            user=self.superuser,
            numbers_text="966501234567",
            status=WhatsAppCheckJob.STATUS_RUNNING,
            pid=proc.pid,
        )
        run_path = wa.job_run_dir(job.id)
        run_path.mkdir(parents=True, exist_ok=True)
        (run_path / "progress.json").write_text(
            json.dumps(
                {
                    "done": True,
                    "totals": {
                        "total": 1,
                        "checked": 1,
                        "live": 1,
                        "errors": 0,
                        "invalid": 0,
                    },
                    "results": [],
                }
            ),
            encoding="utf-8",
        )
        self.client.get(reverse("tools:whatsapp_check_status", args=[job.id]))
        job.refresh_from_db()
        self.assertEqual(job.status, WhatsAppCheckJob.STATUS_COMPLETED)
        r = self.client.get(reverse("tools:whatsapp_check_recent_jobs"))
        self.assertContains(r, "Completed")
        self.assertNotContains(r, ">Running<")

    def test_recent_jobs_partial_shows_user_column_for_admin(self):
        other = User.objects.create_superuser(
            username="other_admin",
            password="pass",
            email="other@example.com",
        )
        WhatsAppCheckJob.objects.create(
            user=other,
            numbers_text="966501234567",
            status=WhatsAppCheckJob.STATUS_COMPLETED,
        )
        r = self.client.get(reverse("tools:whatsapp_check_recent_jobs"))
        self.assertContains(r, ">User<")
        self.assertContains(r, "other_admin")


class WhatsAppAccountOwnershipTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="wa_admin",
            password="pass",
            email="admin@example.com",
        )
        self.other_admin = User.objects.create_superuser(
            username="wa_admin2",
            password="pass",
            email="admin2@example.com",
        )
        self.regular = User.objects.create_user(username="wa_user", password="pass")

    def test_register_account_sets_owner(self):
        wa_accounts.register_account("acc_1", self.regular)
        record = WhatsAppAccount.objects.get(account_name="acc_1")
        self.assertEqual(record.owner, self.regular)

    def test_non_admin_sees_only_owned_linked_accounts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("acc_1", "acc_2"):
                session = root / "sessions" / name
                session.mkdir(parents=True)
                (session / "creds.json").write_text("{}", encoding="utf-8")
            with override_settings(WHATSAPP_ROOT=root):
                wa_accounts.register_account("acc_1", self.regular)
                wa_accounts.register_account("acc_2", self.other_admin)
                names = wa_accounts.linked_account_names_for_user(self.regular)
        self.assertEqual(names, ["acc_1"])

    def test_admin_sees_all_linked_accounts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("acc_1", "acc_2"):
                session = root / "sessions" / name
                session.mkdir(parents=True)
                (session / "creds.json").write_text("{}", encoding="utf-8")
            with override_settings(WHATSAPP_ROOT=root):
                wa_accounts.register_account("acc_1", self.regular)
                wa_accounts.register_account("acc_2", self.other_admin)
                names = wa_accounts.linked_account_names_for_user(self.admin)
        self.assertEqual(names, ["acc_1", "acc_2"])

    def test_admin_account_choices_include_owner_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = root / "sessions" / "acc_1"
            session.mkdir(parents=True)
            (session / "creds.json").write_text("{}", encoding="utf-8")
            with override_settings(WHATSAPP_ROOT=root):
                wa_accounts.register_account("acc_1", self.regular)
                choices = wa_accounts.account_choices_for_form(self.admin)
        self.assertEqual(choices, [("acc_1", "acc_1 (wa_user)")])

    def test_non_admin_cannot_access_other_account(self):
        wa_accounts.register_account("acc_1", self.other_admin)
        self.assertFalse(wa_accounts.user_can_access_account(self.regular, "acc_1"))

    def test_admin_jobs_queryset_includes_all_users(self):
        WhatsAppCheckJob.objects.create(
            user=self.regular,
            numbers_text="966501234567",
            status=WhatsAppCheckJob.STATUS_COMPLETED,
        )
        WhatsAppCheckJob.objects.create(
            user=self.admin,
            numbers_text="966509876543",
            status=WhatsAppCheckJob.STATUS_COMPLETED,
        )
        self.assertEqual(wa_accounts.jobs_queryset_for_user(self.admin).count(), 2)
        self.assertEqual(wa_accounts.jobs_queryset_for_user(self.regular).count(), 1)

    @patch("tools.views.whatsapp_views.wa.start_check_job")
    def test_add_account_registers_owner(self, mock_start):
        mock_start.return_value = MagicMock(pid=1)
        client = Client(enforce_csrf_checks=False)
        client.force_login(self.admin)
        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(WHATSAPP_ROOT=Path(tmp)):
                r = client.post(
                    reverse("tools:whatsapp_check"),
                    {"action": "add_account", "account_name": "acc_9"},
                )
        self.assertEqual(r.status_code, 302)
        record = WhatsAppAccount.objects.get(account_name="acc_9")
        self.assertEqual(record.owner, self.admin)
