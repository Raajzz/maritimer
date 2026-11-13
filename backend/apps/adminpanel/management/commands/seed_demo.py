from django.core.management.base import BaseCommand
from django.db import transaction

from apps.adminpanel.seed import seed_demo


class Command(BaseCommand):
    help = "Seed demo organizations, users and port calls at every pipeline stage (through FDA, disputes and settlement)."

    def add_arguments(self, parser):
        parser.add_argument("--admin-email", default="admin@maritimer.test")
        parser.add_argument("--owner-email", default="owner.demo@maritimer.test")
        parser.add_argument("--agent-email", default="agent.demo@maritimer.test")
        parser.add_argument("--merchant-emails", default="pilots.demo@maritimer.test,supplies.demo@maritimer.test,customs.demo@maritimer.test",
                            help="Three comma-separated emails: pilots/tugs, supplies, customs.")

    def handle(self, *args, **o):
        merchants = [e.strip() for e in o["merchant_emails"].split(",") if e.strip()]
        if len(merchants) != 3:
            self.stderr.write("--merchant-emails needs exactly three addresses")
            return
        with transaction.atomic():
            seed_demo(admin_email=o["admin_email"], owner_email=o["owner_email"], agent_email=o["agent_email"],
                      merchant_emails=merchants, stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS("Demo data ready."))
