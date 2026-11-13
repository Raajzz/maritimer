from django.core.management.base import BaseCommand

from apps.accounts.services import bootstrap_admin


class Command(BaseCommand):
    help = "Create (or promote) the first Admin. They sign in with Google using this email; the account links on first sign-in."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--name", default="")

    def handle(self, *args, email, name, **options):
        user, created = bootstrap_admin(email=email, display_name=name)
        self.stdout.write(self.style.SUCCESS(f"{'Created' if created else 'Promoted'} admin {user.email} (id {user.pk})."))
