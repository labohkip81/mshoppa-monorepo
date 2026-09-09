from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import OutgoingEmail

from .models import AuditEvent, Business, BusinessApplication, Domain, Membership, StoreSettings


@transaction.atomic
def review_application(application_id, reviewer, decision, note):
    application = BusinessApplication.objects.select_related("owner", "business").get(
        pk=application_id
    )
    if application.status == "approved" and decision == "approved":
        return application
    if application.status != "pending":
        raise ValidationError("Only pending applications can be reviewed.")
    if decision == "approved":
        business = Business.objects.create(
            name=application.name,
            slug=application.slug,
            country=application.country,
            currency=application.currency,
        )
        application.business = business
        Membership.objects.create(user=application.owner, business=business, role="owner")
    application.status = decision
    application.review_note = note
    application.reviewed_at = timezone.now()
    application.reviewed_by = reviewer
    application.save()
    AuditEvent.objects.create(
        actor=reviewer,
        business=application.business,
        action=f"application.{decision}",
        object_id=str(application.pk),
        detail={"note": note},
    )
    OutgoingEmail.objects.create(
        recipient=application.owner.email,
        subject=f"Your MSHOPPA application: {application.get_status_display()}",
        body=f"{application.name}: {application.get_status_display()}.\n\n{note}\n\nView your application: {settings.MERCHANT_URL}/applications",
    )
    return application


@transaction.atomic
def provision_business(business_id):
    business = Business.objects.get(pk=business_id)
    if business.provisioning_status == "ready":
        return business
    domain, _ = Domain.objects.get_or_create(
        hostname=f"{business.slug}.{settings.BASE_DOMAIN}",
        defaults={"business": business, "verified": True},
    )
    if domain.business_id != business.pk:
        raise ValueError("Store domain belongs to another business")
    owner = business.memberships.select_related("user").get(role="owner")
    StoreSettings.objects.get_or_create(
        business=business, defaults={"contact_email": owner.user.email}
    )
    business.provisioning_status = "ready"
    business.provisioning_error = ""
    # First successful setup goes online. Retrying an already-ready store returns
    # above, preserving an owner's later offline choice.
    business.published = not business.suspended
    business.save(update_fields=["provisioning_status", "provisioning_error", "published"])
    AuditEvent.objects.create(
        business=business, action="business.provisioned", object_id=str(business.pk)
    )
    return business
