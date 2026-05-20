import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from tools.models import WhatsAppCheckJob
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

    def test_is_process_running_false_after_child_exits(self):
        proc = subprocess.Popen(
            [sys.executable, "-c", "pass"],
            start_new_session=True,
        )
        pid = proc.pid
        proc.wait()
        self.assertFalse(wa.is_process_running(pid))

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
    @patch("tools.views.whatsapp_views.wa.list_accounts")
    def test_accounts_status_partial_renders_online(
        self, mock_list, mock_status, mock_refresh
    ):
        mock_list.return_value = [
            wa.WhatsAppAccountInfo(
                name="acc_1",
                has_session=True,
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
        mock_refresh.assert_called_once()
        self.assertEqual(mock_refresh.call_args.kwargs["max_age_seconds"], 45)

    def test_accounts_tab_shows_interval_input(self):
        r = self.client.get(reverse("tools:whatsapp_check"), {"tab": "accounts"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Status check interval (seconds)")
        self.assertContains(r, 'name="seconds"')


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
