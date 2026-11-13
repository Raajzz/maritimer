from django.core.management.base import BaseCommand

from apps.requests.services import expire_due_requests


class Command(BaseCommand):
    help = "Expire PENDING requests whose expires_at has passed (run from a scheduler)."

    def handle(self, *args, **options):
        count = expire_due_requests()
        self.stdout.write(self.style.SUCCESS(f"Expired {count} request(s)."))
