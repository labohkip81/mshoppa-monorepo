import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import EmailChallenge, OutgoingEmail


def verification_email(user):
    token = secrets.token_urlsafe(32)
    EmailChallenge.objects.create(
        user=user,
        digest=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=timezone.now() + timedelta(hours=1),
    )
    OutgoingEmail.objects.create(
        recipient=user.email,
        subject="Verify your MSHOPPA email",
        body=f"Welcome to MSHOPPA, {user.first_name}.\n\nVerify your email to apply for your store:\n{settings.MERCHANT_URL}/verify-email?token={token}\n\nThis link expires in one hour.",
    )
