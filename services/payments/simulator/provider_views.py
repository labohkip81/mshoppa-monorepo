import hmac
import json
import uuid
from decimal import Decimal

import stripe
from apps.checkout.protocol import ensure_local, verify_request
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .configuration import for_session
from .models import PaymentSession
from .providers import (
    ProviderUnavailable,
    StripeAdapter,
    VentyMpesaAdapter,
    adapter,
    provider_config,
)
from .views import deliver_event, session_data


class ProvidersView(APIView):
    def post(self, request):
        verify_request(request)
        business_id = serializers.UUIDField().run_validation(request.data.get("business_id"))
        return Response(provider_config(business_id))


class StartInput(serializers.Serializer):
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")


class StartPaymentView(APIView):
    def post(self, request, token):
        ensure_local()
        SessionAuthentication().enforce_csrf(request)
        data = StartInput(data=request.data)
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            session = get_object_or_404(PaymentSession, token=token)
            if session.status != "pending" or session.expires_at <= timezone.now():
                raise ValidationError("This payment is complete or expired.")
            if session.external_id:
                return Response(session_data(session))
            if session.initiation_state in {"starting", "unknown"}:
                raise ValidationError(
                    "A payment request is already in progress. Check its status; do not send another request."
                )
            provider = adapter(session)
            provider.validate(session)
            phone = (
                provider.phone(data.validated_data["phone"]) if session.backend == "venty" else ""
            )
            session.phone = phone
            session.initiation_state = "starting"
            session.save(update_fields=["phone", "initiation_state"])
        try:
            result = provider.start(session, phone)
        except (ProviderUnavailable, ValidationError) as error:
            # Venty does not deduplicate transaction_id; a timeout must never cause a second STK.
            PaymentSession.objects.filter(pk=session.pk).update(
                initiation_state="new" if session.backend == "stripe" else "unknown"
            )
            return Response(
                {
                    "detail": str(error)
                    if isinstance(error, ProviderUnavailable)
                    else "The provider could not start this checkout."
                },
                status=503,
            )
        PaymentSession.objects.filter(pk=session.pk).update(**result, initiation_state="started")
        session.refresh_from_db()
        return Response(session_data(session))


def confirmed_event(session, status):
    if status == "pending":
        return Response(session_data(session))
    return deliver_event(
        {
            "session_id": session.pk,
            "event_id": session.event_id
            or uuid.uuid5(uuid.NAMESPACE_URL, f"mshoppa:{session.pk}:{status}"),
            "status": status,
        },
        session.provider,
        verified_provider=True,
    )


class RefreshPaymentView(APIView):
    def post(self, request, token):
        ensure_local()
        SessionAuthentication().enforce_csrf(request)
        session = get_object_or_404(PaymentSession, token=token)
        if session.backend == "simulator":
            return Response(session_data(session))
        if session.event_id:
            return confirmed_event(session, session.status)
        if not session.external_id:
            return Response(session_data(session))
        try:
            status = adapter(session).status(session)
        except ProviderUnavailable as error:
            return Response({"detail": str(error)}, status=503)
        return confirmed_event(session, status)


class StripeWebhookView(APIView):
    def post(self, request):
        ensure_local()
        try:
            candidate = json.loads(request.body)
            external_id = candidate['data']['object']['id']
        except (ValueError, KeyError, TypeError):
            raise PermissionDenied('Invalid Stripe webhook.')
        session = PaymentSession.objects.filter(external_id=external_id, backend='stripe').first()
        secret = for_session(session)['webhook_secret'] if session else ''
        if not secret:
            raise PermissionDenied("Stripe webhook verification is not configured.")
        try:
            event = stripe.Webhook.construct_event(
                request.body,
                request.headers.get("Stripe-Signature", ""),
                secret,
            )
        except (ValueError, stripe.SignatureVerificationError):
            raise PermissionDenied("Invalid Stripe webhook signature.")
        event = event.to_dict()
        if event.get("livemode") is not False:
            raise PermissionDenied("Only Stripe test events are accepted.")
        if event["type"] not in {
            "checkout.session.completed",
            "checkout.session.expired",
            "checkout.session.async_payment_succeeded",
        }:
            return Response({"received": True})
        data = event["data"]["object"]
        session = get_object_or_404(PaymentSession, external_id=data["id"], backend="stripe")
        status = StripeAdapter().verify(session, data)
        return confirmed_event(session, status)


class VentyCallbackInput(serializers.Serializer):
    order_number = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    payment_status = serializers.ChoiceField(choices=["paid", "failed"])
    mpesa_receipt_number = serializers.CharField(
        max_length=100, required=False, allow_blank=True, default=""
    )


class VentyWebhookView(APIView):
    def post(self, request):
        ensure_local()
        data = VentyCallbackInput(data=request.data)
        data.is_valid(raise_exception=True)
        payload = data.validated_data
        session = get_object_or_404(PaymentSession, pk=payload['order_number'], backend='venty')
        secret = for_session(session)['callback_secret']
        if not secret or not hmac.compare_digest(
            secret, request.headers.get("X-Payment-Callback-Secret", "")
        ):
            raise PermissionDenied("Invalid Venty callback secret.")
        if session.initiation_state == "new" or payload["amount"] != Decimal(session.amount):
            raise ValidationError("Venty callback does not match a payment request.")
        status = "succeeded" if payload["payment_status"] == "paid" else "failed"
        if status == "succeeded" and not payload["mpesa_receipt_number"]:
            raise ValidationError("A successful M-Pesa payment requires a receipt.")
        # When possible, corroborate the shared-secret callback with the saved provider record.
        if session.external_id:
            try:
                if VentyMpesaAdapter().status(session) != status:
                    raise ValidationError("Venty callback and payment record disagree.")
            except ProviderUnavailable as error:
                return Response({"detail": str(error)}, status=503)
        response = confirmed_event(session, status)
        if response.status_code == 200:
            PaymentSession.objects.filter(pk=session.pk).update(
                receipt_number=payload["mpesa_receipt_number"]
            )
        return response
