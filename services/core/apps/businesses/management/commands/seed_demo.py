from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.businesses.models import BusinessApplication
from apps.businesses.services import provision_business, review_application


class Command(BaseCommand):
    help = "Create local-only demo accounts, two stores, and one pending application."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Demo seeding is disabled outside development.")
        users = []
        for email, name, staff in [
            ("owner@example.test", "Alex", False),
            ("second@example.test", "Sam", False),
            ("reviewer@example.test", "Morgan", True),
        ]:
            user, created = get_user_model().objects.get_or_create(
                username=email,
                defaults={
                    "email": email,
                    "first_name": name,
                    "email_verified": True,
                    "is_staff": staff,
                },
            )
            if created:
                user.set_password("Local-Mshoppa-2026!")
                user.save()
            users.append(user)
        for owner, name, slug in [
            (users[0], "Everyday Studio", "everyday-studio"),
            (users[1], "Field & Form", "field-and-form"),
        ]:
            app, created = BusinessApplication.objects.get_or_create(
                slug=slug,
                defaults={
                    "owner": owner,
                    "name": name,
                    "category": "Lifestyle",
                    "phone": "+254700000000",
                    "country": "KE",
                    "currency": "KES",
                    "status": "pending",
                },
            )
            if created:
                app = review_application(app.pk, users[2], "approved", "Local demonstration store")
            if app.business_id:
                provision_business(app.business_id)
        BusinessApplication.objects.get_or_create(
            slug="linen-house",
            defaults={
                "owner": users[0],
                "name": "Linen House",
                "category": "Home & living",
                "phone": "+254711000000",
                "country": "KE",
                "currency": "KES",
                "description": "Thoughtful essentials for the everyday home.",
                "status": "pending",
            },
        )
        self.stdout.write(
            "Local demo ready. See README for local credentials. Reviewer MFA enrollment is required on first login."
        )
