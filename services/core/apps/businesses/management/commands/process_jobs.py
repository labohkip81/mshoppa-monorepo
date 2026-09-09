import time

from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import OutgoingEmail
from apps.businesses.models import Business
from apps.businesses.services import provision_business


class Command(BaseCommand):
    help = "Process durable provisioning and local mail jobs. Use one worker for the SQLite pilot."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        while True:
            from apps.checkout.views import expire_orders

            expire_orders()
            for business_id in Business.objects.filter(provisioning_status="queued").values_list(
                "pk", flat=True
            ):
                try:
                    provision_business(business_id)
                except Exception as error:
                    Business.objects.filter(pk=business_id).update(
                        provisioning_status="failed", provisioning_error=type(error).__name__
                    )
                    self.stderr.write(
                        f"Provisioning failed for {business_id}: {type(error).__name__}"
                    )
            # SQLite initial phase: one worker, bounded batch; delivery is at-least-once.
            for email_id in list(
                OutgoingEmail.objects.filter(sent_at=None, attempts__lt=5).values_list(
                    "pk", flat=True
                )[:20]
            ):
                with transaction.atomic():
                    email = OutgoingEmail.objects.get(pk=email_id)
                    if email.sent_at:
                        continue
                    email.attempts += 1
                    email.save(update_fields=["attempts"])
                # Never hold SQLite's write lock during an external delivery call.
                try:
                    send_mail(
                        email.subject, email.body, None, [email.recipient], fail_silently=False
                    )
                    email.sent_at = timezone.now()
                    email.last_error = ""
                except Exception as error:
                    email.last_error = type(error).__name__
                email.save(update_fields=["sent_at", "last_error"])
            if options["once"]:
                return
            time.sleep(2)
