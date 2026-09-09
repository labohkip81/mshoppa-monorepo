import uuid
from urllib.error import URLError
from urllib.parse import urlsplit

from apps.checkout.protocol import ensure_local, signed_post, verify_request
from django.conf import settings
from django.db import transaction
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .configuration import encrypt_values, for_session, latest, values
from .models import PaymentSession


def session_data(session):
    return {
        "session_id": str(session.pk),
        "order_number": str(session.order_id)[:8].upper(),
        "store_name": session.store_name,
        "provider": session.provider,
        "amount": str(session.amount),
        "currency": session.currency,
        "status": session.status,
        "order_status": session.order_status,
        "delivered": session.delivered,
        "expired": session.expires_at <= timezone.now(),
        "return_url": session.return_url,
        "test_mode": session.backend != "venty",
        "backend": session.backend,
        "external_id": session.external_id,
        "redirect_url": session.redirect_url,
        "initiation_state": session.initiation_state,
        "receipt_number": session.receipt_number,
        "provider_ready": (session.backend == "simulator" or bool(for_session(session)["enabled"] and for_session(session).get("secret_key" if session.provider == "stripe" else "tenant_id"))),
    }


class SessionInput(serializers.Serializer):
    order_id = serializers.UUIDField()
    business_id = serializers.UUIDField(required=False, allow_null=True)
    store_name = serializers.CharField(max_length=120)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0)
    currency = serializers.CharField(max_length=3)
    provider = serializers.ChoiceField(choices=["stripe", "mpesa"])
    expires_at = serializers.DateTimeField()
    return_url = serializers.CharField(max_length=500)

    def validate_return_url(self, value):
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        if (
            parsed.scheme != "http"
            or not (host == "localhost" or host.endswith(".localhost"))
            or parsed.port != 4203
            or parsed.username
            or parsed.password
        ):
            raise serializers.ValidationError(
                "The simulator can return only to a local storefront on port 4203."
            )
        return value


class SessionCreateView(APIView):
    def post(self, request):
        verify_request(request)
        serializer = SessionInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            session, created = PaymentSession.objects.get_or_create(
                order_id=data["order_id"],
                defaults={
                    **data,
                    "encrypted_credentials": encrypt_values(values(data["provider"], data.get("business_id"))),
                    "configuration": latest(data["business_id"], data["provider"]) if data.get("business_id") else None,
                    "backend": settings.STRIPE_PAYMENT_BACKEND
                    if data["provider"] == "stripe"
                    else settings.MPESA_PAYMENT_BACKEND,
                },
            )
            if not created and any(getattr(session, key) != value for key, value in data.items()):
                raise ValidationError("This order already has a different payment session.")
        return Response(
            {
                "session_id": str(session.pk),
                "backend": session.backend,
                "payment_url": settings.PAYMENT_PUBLIC_URL + "/?session=" + session.token,
            }
        )


class SessionView(APIView):
    def get(self, request, token):
        ensure_local()
        return Response(session_data(get_object_or_404(PaymentSession, token=token)))


class CsrfView(APIView):
    def get(self, request):
        return Response({"token": get_token(request._request)})


class EventInput(serializers.Serializer):
    event_id = serializers.UUIDField()
    session_id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=["succeeded", "failed"])


def deliver_event(data, provider=None, verified_provider=False):
    with transaction.atomic():
        session = get_object_or_404(PaymentSession, pk=data["session_id"])
        if not verified_provider and session.backend != "simulator":
            raise ValidationError("Provider sessions cannot be completed through the simulator.")
        if provider and provider != session.provider:
            raise ValidationError("Webhook provider does not match the payment session.")
        if (
            session.expires_at <= timezone.now()
            and data["status"] == "succeeded"
            and not verified_provider
        ):
            raise ValidationError("This local session has expired. Return to checkout.")
        if session.event_id and (
            session.event_id != data["event_id"] or session.status != data["status"]
        ):
            raise ValidationError(
                "This session already has a terminal event. Retry its existing webhook instead."
            )
        session.event_id, session.status = data["event_id"], data["status"]
        session.save(update_fields=["event_id", "status"])
    payload = {
        "event_id": str(session.event_id),
        "session_id": str(session.pk),
        "order_id": str(session.order_id),
        "status": session.status,
        "provider": session.provider,
        "amount": str(session.amount),
        "currency": session.currency,
    }
    try:
        result = signed_post(settings.CORE_PAYMENT_CALLBACK_URL, payload)
    except (URLError, TimeoutError, OSError, ValueError):
        return Response(
            {
                "detail": "The payment result is saved, but its webhook could not be delivered. Retry webhook delivery."
            },
            status=503,
        )
    session.delivered = True
    session.order_status = result["status"]
    session.save(update_fields=["delivered", "order_status"])
    return Response(session_data(session))


class SimulateView(APIView):
    def post(self, request, token):
        ensure_local()
        SessionAuthentication().enforce_csrf(request)
        session = get_object_or_404(PaymentSession, token=token)
        status = request.data.get("status")
        if status not in {"succeeded", "failed"}:
            raise ValidationError("Choose succeeded or failed.")
        return deliver_event(
            {
                "event_id": session.event_id or uuid.uuid4(),
                "session_id": session.pk,
                "status": status,
            }
        )


class DummyProviderWebhookView(APIView):
    def post(self, request, provider):
        verify_request(request)
        serializer = EventInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        return deliver_event(serializer.validated_data, provider)
