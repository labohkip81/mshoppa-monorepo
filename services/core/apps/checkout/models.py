import secrets
import uuid

from django.db import models


def access_token():
    return secrets.token_urlsafe(32)


class Order(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey("businesses.Business", on_delete=models.PROTECT)
    token = models.CharField(max_length=64, default=access_token, unique=True)
    checkout_key = models.UUIDField()
    request_hash = models.CharField(max_length=64)
    email = models.EmailField()
    customer_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30, blank=True)
    address = models.CharField(max_length=500)
    currency = models.CharField(max_length=3)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2)
    tax = models.DecimalField(max_digits=14, decimal_places=2)
    total = models.DecimalField(max_digits=14, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2)
    provider = models.CharField(max_length=12)
    payment_backend = models.CharField(max_length=16, default='simulator')
    payment_review_required = models.BooleanField(default=False)
    status = models.CharField(max_length=20, default="pending")
    fulfillment_status = models.CharField(max_length=20, default="unfulfilled")
    staff_notes = models.TextField(blank=True, max_length=4000)
    tracking_reference = models.CharField(max_length=200, blank=True)
    payment_url = models.URLField(max_length=500, blank=True)
    session_id = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["business", "checkout_key"], name="unique_checkout_request"
            )
        ]


class OrderLine(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="lines")
    variant = models.ForeignKey("catalog.Variant", on_delete=models.PROTECT)
    product_name = models.CharField(max_length=180)
    variant_name = models.CharField(max_length=120)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=14, decimal_places=2)


class PaymentEvent(models.Model):
    event_id = models.UUIDField(unique=True)
    order = models.ForeignKey(Order, on_delete=models.PROTECT)
    payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
