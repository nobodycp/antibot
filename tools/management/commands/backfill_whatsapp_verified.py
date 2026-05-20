from django.core.management.base import BaseCommand

from tools.services import whatsapp_service as wa


class Command(BaseCommand):
    help = "Import verified_active_numbers.txt from all WhatsApp run directories into history."

    def handle(self, *args, **options):
        count = wa.backfill_verified_history_from_runs()
        self.stdout.write(
            self.style.SUCCESS(f"Backfill complete: {count} new verified number(s).")
        )
