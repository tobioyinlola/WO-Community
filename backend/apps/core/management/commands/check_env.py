from django.core.management.base import BaseCommand, CommandError

from config.env_check import main


class Command(BaseCommand):
    help = (
        "Check the environment against the production rules and print every missing or invalid "
        "variable at once. It does not start the server. Exit code 1 when anything is wrong."
    )

    def handle(self, *args, **options):
        if main():
            raise CommandError("The environment is not ready for production.")
