import secrets
import uuid

from django.db import models


def session_token():
    return secrets.token_urlsafe(32)


class PaymentConfiguration(models.Model):
    business_id = models.UUIDField(db_index=True)
    provider = models.CharField(max_length=12)
    encrypted_values = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-id']


class PaymentSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    token = models.CharField(max_length=64, default=session_token, unique=True)
    order_id = models.UUIDField(unique=True)
    business_id = models.UUIDField(null=True, db_index=True)
    configuration = models.ForeignKey(PaymentConfiguration, null=True, on_delete=models.PROTECT)
    encrypted_credentials = models.TextField(blank=True)
    store_name = models.CharField(max_length=120)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3)
    provider = models.CharField(max_length=12)
    return_url = models.URLField(max_length=500)
    backend = models.CharField(max_length=16, default='simulator')
    external_id = models.CharField(max_length=255, blank=True, db_index=True)
    redirect_url = models.URLField(max_length=2000, blank=True)
    initiation_state = models.CharField(max_length=16, default='new')
    phone = models.CharField(max_length=20, blank=True)
    receipt_number = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=16, default="pending")
    order_status = models.CharField(max_length=16, default="pending")
    event_id = models.UUIDField(null=True)
    delivered = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
