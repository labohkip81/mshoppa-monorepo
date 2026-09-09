import hashlib
import json
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from urllib.error import URLError

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.views import CsrfAPIView
from apps.businesses.models import Domain
from apps.catalog.models import Variant
from apps.catalog.serializers import ProductImageSerializer

from .models import Order, OrderLine, PaymentEvent
from .protocol import ensure_local, signed_post, verify_request


def store_domain(request):
    hostname = request.get_host().split(":", 1)[0].lower().rstrip(".")
    return get_object_or_404(
        Domain.objects.select_related("business__store_settings"),
        hostname=hostname,
        verified=True,
        business__published=True,
        business__suspended=False,
        business__provisioning_status="ready",
    )


class CartItemSerializer(serializers.Serializer):
    variant_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1, max_value=99)


class QuoteSerializer(serializers.Serializer):
    items = CartItemSerializer(many=True, allow_empty=False, max_length=50)


class CheckoutSerializer(QuoteSerializer):
    checkout_key = serializers.UUIDField()
    quote_token = serializers.CharField(max_length=2000)
    name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    address = serializers.CharField(max_length=500)
    provider = serializers.ChoiceField(choices=["stripe", "mpesa"])


def quote(business, items):
    ids = [item["variant_id"] for item in items]
    if len(set(ids)) != len(ids):
        raise ValidationError("Combine quantities for repeated variants.")
    variants = {
        v.pk: v
        for v in Variant.objects.filter(
            pk__in=ids, is_active=True, product__business=business, product__status="published"
        )
        .select_related("product")
        .prefetch_related("product__images", "product__variants")
    }
    lines, subtotal = [], Decimal("0")
    quantum = Decimal("1") if business.currency in {"UGX", "RWF"} else Decimal("0.01")
    for item in items:
        variant = variants.get(item["variant_id"])
        if not variant:
            raise ValidationError("A cart item is no longer available. Remove it and try again.")
        quantity = item["quantity"]
        if quantity > variant.stock:
            raise ValidationError(
                f"{variant.product.name} ({variant.label}): only {variant.stock} available."
            )
        price = variant.offer_price if variant.offer_price is not None else variant.price
        total = price * quantity
        subtotal += total
        image = next(iter(variant.product.images.all()), None)
        lines.append(
            {
                "variant_id": str(variant.pk),
                "product_name": variant.product.name,
                "variant_name": variant.label,
                "quantity": quantity,
                "unit_price": str(price),
                "line_total": str(total),
                "stock": variant.stock,
                "variants": [
                    {"id": str(option.pk), "label": option.label, "price": str(option.offer_price if option.offer_price is not None else option.price), "stock": option.stock}
                    for option in variant.product.variants.all() if option.is_active
                ],
                "image_url": ProductImageSerializer(image).data["url"] if image else "",
            }
        )
    rate = business.store_settings.tax_rate
    tax = (subtotal * rate / 100).quantize(quantum, rounding=ROUND_HALF_UP)
    total = subtotal + tax
    if total > Decimal("9999999999.99"):
        raise ValidationError("This cart exceeds the supported order total.")
    methods = [p for p in ["stripe", "mpesa"] if getattr(business.store_settings, f"{p}_enabled")]
    result = {
        "lines": lines,
        "subtotal": str(subtotal),
        "tax": str(tax),
        "tax_rate": str(rate),
        "total": str(total),
        "currency": business.currency,
        "methods": methods,
    }
    snapshot = {
        "business": str(business.pk),
        "currency": business.currency,
        "tax_rate": str(rate),
        "total": str(total),
        "items": sorted(
            [(line["variant_id"], line["quantity"], line["unit_price"]) for line in lines]
        ),
    }
    digest = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
    result["quote_token"] = signing.dumps({"digest": digest}, salt="checkout.quote")
    return result, digest


def order_data(order):
    return {
        "id": str(order.pk),
        "order_number": str(order.pk)[:8].upper(),
        "token": order.token,
        "status": order.status,
        "provider": order.provider,
        "created_at": order.created_at.isoformat(),
        "fulfillment_status": order.fulfillment_status,
        "tracking_reference": order.tracking_reference,
        "currency": order.currency,
        "subtotal": str(order.subtotal),
        "tax": str(order.tax),
        "total": str(order.total),
        "payment_url": order.payment_url if order.status == "pending" else "",
        "test_mode": order.payment_backend != "venty",
        "payment_review_required": order.payment_review_required,
        "lines": list(
            order.lines.values(
                "product_name", "variant_name", "quantity", "unit_price", "line_total"
            )
        ),
    }


def close_order(order, status):
    if order.status != "pending":
        return
    if status != "paid":
        for line in order.lines.all():
            Variant.objects.filter(pk=line.variant_id).update(stock=F("stock") + line.quantity)
    order.status = status
    order.save(update_fields=["status"])


def expire_orders():
    with transaction.atomic():
        for order in Order.objects.filter(status="pending", expires_at__lte=timezone.now()):
            close_order(order, "expired")


class GuestView(CsrfAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []


class CartQuoteView(GuestView):
    @extend_schema(request=QuoteSerializer, responses={200: {"type": "object"}})
    def post(self, request):
        ensure_local()
        business = store_domain(request).business
        serializer = QuoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        expire_orders()
        result, _ = quote(business, serializer.validated_data["items"])
        return Response(result)


class CheckoutView(GuestView):
    @extend_schema(request=CheckoutSerializer, responses={201: {"type": "object"}})
    def post(self, request):
        ensure_local()
        domain = store_domain(request)
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return create_checkout(domain, serializer.validated_data)


def create_checkout(domain, data, order_id=None):
    try:
        confirmed = signing.loads(data["quote_token"], salt="checkout.quote", max_age=600)
    except signing.BadSignature:
        raise ValidationError("Your quote has expired. Review the totals and try again.")
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "quote": confirmed,
                "name": data["name"],
                "email": data["email"],
                "address": data["address"],
                "phone": data["phone"],
                "provider": data["provider"],
                "items": [
                    (str(item["variant_id"]), item["quantity"]) for item in data["items"]
                ],
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    with transaction.atomic():
        existing = Order.objects.filter(
            business=domain.business, checkout_key=data["checkout_key"]
        ).first()
        if existing:
            if existing.request_hash != fingerprint:
                raise ValidationError(
                    "This checkout attempt already exists with different details. Start a new checkout."
                )
            order = existing
        else:
            totals, digest = quote(domain.business, data["items"])
            if digest != confirmed["digest"]:
                raise ValidationError(
                    "Prices or taxes changed. Refresh your totals before paying."
                )
            if data["provider"] not in totals["methods"]:
                raise ValidationError("This payment method is not enabled for this store.")
            order = Order.objects.create(
                **({"id": order_id} if order_id is not None else {}),
                business=domain.business,
                checkout_key=data["checkout_key"],
                request_hash=fingerprint,
                email=data["email"],
                customer_name=data["name"],
                address=data["address"],
                phone=data["phone"],
                currency=totals["currency"],
                subtotal=totals["subtotal"],
                tax=totals["tax"],
                total=totals["total"],
                tax_rate=totals["tax_rate"],
                provider=data["provider"],
                expires_at=timezone.now() + timedelta(minutes=35),
            )
            for line in totals["lines"]:
                updated = Variant.objects.filter(
                    pk=line["variant_id"], stock__gte=line["quantity"]
                ).update(stock=F("stock") - line["quantity"])
                if not updated:
                    raise ValidationError("Stock changed. Review your cart and try again.")
                OrderLine.objects.create(
                    order=order,
                    **{
                        k: line[k]
                        for k in [
                            "variant_id",
                            "product_name",
                            "variant_name",
                            "quantity",
                            "unit_price",
                            "line_total",
                        ]
                    },
                )
    if order.status == "pending" and not order.payment_url:
        try:
            session = signed_post(
                settings.PAYMENT_SERVICE_URL + "/api/sessions/",
                {
                    "order_id": str(order.pk),
                    "business_id": str(order.business_id),
                    "store_name": domain.business.name,
                    "amount": str(order.total),
                    "currency": order.currency,
                    "provider": order.provider,
                    "expires_at": order.expires_at.isoformat(),
                    "return_url": settings.STOREFRONT_URL_PATTERN.format(
                        hostname=domain.hostname
                    ).rstrip("/")
                    + "/checkout?order="
                    + order.token,
                },
            )
            order.payment_backend = session.get("backend", "simulator")
            order.session_id = session["session_id"]
            order.payment_url = session["payment_url"]
            order.save(update_fields=["session_id", "payment_url", "payment_backend"])
        except (URLError, TimeoutError, OSError, ValueError, KeyError):
            # Keep the reservation and same idempotency key for safe retries.
            return Response(
                {
                    "detail": "The payment service is unavailable. Retry this checkout; your reservation expires in 35 minutes."
                },
                status=503,
            )
    return Response(order_data(order), status=201)


class OrderStatusView(GuestView):
    @extend_schema(responses={200: {"type": "object"}})
    def get(self, request, token):
        business = store_domain(request).business
        expire_orders()
        return Response(order_data(get_object_or_404(Order, business=business, token=token)))


class WebhookSerializer(serializers.Serializer):
    event_id = serializers.UUIDField()
    order_id = serializers.UUIDField()
    session_id = serializers.CharField(max_length=100)
    provider = serializers.ChoiceField(choices=["stripe", "mpesa"])
    status = serializers.ChoiceField(choices=["succeeded", "failed"])
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0)
    currency = serializers.CharField(max_length=3)


class DummyWebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(request=WebhookSerializer, responses={200: {"type": "object"}})
    def post(self, request):
        verify_request(request)
        serializer = WebhookSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            order = get_object_or_404(Order, pk=data["order_id"])
            if (
                order.session_id != data["session_id"]
                or order.provider != data["provider"]
                or order.currency != data["currency"]
                or order.total != data["amount"]
            ):
                raise ValidationError("Payment event does not match this order.")
            prior = PaymentEvent.objects.filter(event_id=data["event_id"]).first()
            if prior:
                if prior.payload != request.data:
                    raise ValidationError("Event ID has already been used for a different payload.")
                return Response({"received": True, "status": order.status})
            PaymentEvent.objects.create(
                event_id=data["event_id"], order=order, payload=request.data
            )
            if data['status'] == 'succeeded' and order.status != 'paid' and (order.status in {'expired', 'failed'} or order.expires_at <= timezone.now()):
                order.payment_review_required = True
                order.save(update_fields=['payment_review_required'])
            if order.expires_at <= timezone.now():
                close_order(order, "expired")
            else:
                close_order(order, "paid" if data["status"] == "succeeded" else "failed")
        return Response({"received": True, "status": order.status})
