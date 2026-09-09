import uuid

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower


class Business(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=50, unique=True)
    currency = models.CharField(max_length=3)
    country = models.CharField(max_length=2)
    provisioning_status = models.CharField(max_length=12, default="queued")
    provisioning_error = models.CharField(max_length=200, blank=True)
    suspended = models.BooleanField(default=False)
    published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class BusinessApplication(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending", "Pending review"
        CHANGES = "changes_requested", "Changes requested"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    business = models.OneToOneField(Business, on_delete=models.PROTECT, null=True)
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=50, unique=True)
    category = models.CharField(max_length=60)
    phone = models.CharField(max_length=30)
    country = models.CharField(max_length=2)
    currency = models.CharField(max_length=3)
    description = models.TextField(max_length=2000, blank=True)
    status = models.CharField(max_length=20, choices=Status, default=Status.DRAFT)
    review_note = models.TextField(blank=True)
    submitted_at = models.DateTimeField(null=True)
    reviewed_at = models.DateTimeField(null=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reviews", null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(Lower("slug"), name="unique_application_slug_ci")]


class Membership(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(
        max_length=20,
        choices=[(v, v.title()) for v in ["owner", "manager", "fulfillment", "support"]],
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "business"], name="one_membership_per_business")
        ]


class Domain(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="domains")
    hostname = models.CharField(max_length=253, unique=True)
    verified = models.BooleanField(default=False)
    is_primary = models.BooleanField(default=True)


def store_logo_path(instance, filename):
    return f"stores/{instance.business_id}/logos/{uuid.uuid4()}.webp"


def store_cover_path(instance, filename):
    return f"stores/{instance.business_id}/covers/{uuid.uuid4()}.webp"


class StoreSettings(models.Model):
    business = models.OneToOneField(
        Business, on_delete=models.CASCADE, related_name="store_settings"
    )
    headline = models.CharField(max_length=160, default="Made for your everyday.")
    description = models.TextField(blank=True)
    contact_email = models.EmailField(blank=True)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    stripe_enabled = models.BooleanField(default=True)
    mpesa_enabled = models.BooleanField(default=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    contact_address = models.CharField(max_length=300, blank=True)
    whatsapp_number = models.CharField(max_length=30, blank=True)
    logo = models.FileField(upload_to=store_logo_path, blank=True)
    cover = models.FileField(upload_to=store_cover_path, blank=True)
    instagram_url = models.URLField(blank=True)
    facebook_url = models.URLField(blank=True)
    tiktok_url = models.URLField(blank=True)
    x_url = models.URLField(blank=True)
    linkedin_url = models.URLField(blank=True)
    return_refund_policy = models.TextField(blank=True)
    privacy_policy = models.TextField(blank=True)
    terms_conditions = models.TextField(blank=True)
    theme_id = models.CharField(max_length=30, default="natural-01")
    surface_tone = models.CharField(max_length=12, default="taupe")
    featured_product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="featured_in_stores",
    )


class AuditEvent(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True)
    business = models.ForeignKey(Business, on_delete=models.PROTECT, null=True)
    action = models.CharField(max_length=80)
    object_id = models.CharField(max_length=80)
    detail = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class WalletSettlement(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.PROTECT)
    order = models.OneToOneField('checkout.Order', on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3)
    reference = models.CharField(max_length=200)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0), name='positive_wallet_settlement')]


class Withdrawal(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.PROTECT)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    request_key = models.UUIDField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3)
    method = models.CharField(max_length=12, choices=[('mpesa', 'M-Pesa'), ('bank', 'Bank')])
    recipient_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=20, blank=True)
    bank_name = models.CharField(max_length=120, blank=True)
    account_number = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=12, default='pending', choices=[(v, v.title()) for v in ['pending', 'completed', 'rejected', 'cancelled']])
    transfer_reference = models.CharField(max_length=200, blank=True)
    review_note = models.CharField(max_length=500, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, related_name='withdrawal_reviews')
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True)

    class Meta:
        ordering = ['-created_at', '-id']
        constraints = [
            models.UniqueConstraint(fields=['business', 'request_key'], name='unique_store_withdrawal_request'),
            models.CheckConstraint(condition=models.Q(amount__gt=0), name='positive_withdrawal'),
        ]
