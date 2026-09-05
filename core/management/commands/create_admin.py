import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create the initial Django superuser if it does not already exist."

    def handle(self, *args, **options):
        User = get_user_model()

        email = os.environ.get("DJANGO_SUPERUSER_EMAIL")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")

        if not email or not password:
            self.stdout.write(
                self.style.WARNING(
                    "DJANGO_SUPERUSER_EMAIL or DJANGO_SUPERUSER_PASSWORD is not set."
                )
            )
            return

        if User.objects.filter(email=email).exists():
            self.stdout.write(
                self.style.SUCCESS(
                    f"Superuser with email '{email}' already exists."
                )
            )
            return

        User.objects.create_superuser(
            email=email,
            password=password,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Superuser with email '{email}' created successfully."
            )
        )