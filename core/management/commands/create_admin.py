import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create or upgrade the initial Django superuser."

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

        user = User.objects.filter(email=email).first()

        if user:
            user.is_staff = True
            user.is_superuser = True
            user.role = "super_admin"
            user.must_change_password = False
            user.save(
                update_fields=[
                    "is_staff",
                    "is_superuser",
                    "role",
                    "must_change_password",
                ]
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f"User '{email}' upgraded to superuser successfully."
                )
            )
            return

        User.objects.create_superuser(
            email=email,
            password=password,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Superuser '{email}' created successfully."
            )
        )