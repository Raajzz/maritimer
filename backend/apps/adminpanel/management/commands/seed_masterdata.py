from django.core.management.base import BaseCommand

from apps.adminpanel.seed import seed_masterdata


class Command(BaseCommand):
    help = "Idempotently load countries, currencies, locations, ports, service categories, cargo types and request policies."

    def handle(self, *args, **options):
        seed_masterdata(self.stdout)
        self.stdout.write(self.style.SUCCESS("Master data ready."))
