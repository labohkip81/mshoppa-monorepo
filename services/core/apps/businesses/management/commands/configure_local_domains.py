from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.businesses.models import Business, Domain


class Command(BaseCommand):
    help = "Add <slug>.localhost aliases to existing local stores without removing old domains."

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG or settings.BASE_DOMAIN != "localhost":
            raise CommandError(
                "This command is only available in local development with BASE_DOMAIN=localhost."
            )
        for business in Business.objects.filter(provisioning_status="ready"):
            domain, _ = Domain.objects.get_or_create(
                hostname=f"{business.slug}.localhost",
                defaults={"business": business, "verified": True, "is_primary": True},
            )
            if domain.business_id != business.pk:
                raise CommandError(f"Domain {domain.hostname} already belongs to another store.")
            Domain.objects.filter(business=business).exclude(pk=domain.pk).update(is_primary=False)
            domain.is_primary = True
            domain.verified = True
            domain.save(update_fields=["is_primary", "verified"])
            self.stdout.write(f"{domain.hostname}:4203")
