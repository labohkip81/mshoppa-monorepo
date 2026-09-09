"""Signed cart handoff from a storefront to the shared payments page."""
import uuid

from django.conf import settings
from django.core import signing
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.businesses.models import Domain

from .models import Order
from .protocol import ensure_local, verify_request
from .views import (
    CheckoutSerializer,
    GuestView,
    QuoteSerializer,
    create_checkout,
    expire_orders,
    order_data,
    quote,
    store_domain,
)

SALT = 'checkout.payment-handoff.v1'


def store_url(domain):
    return settings.STOREFRONT_URL_PATTERN.format(hostname=domain.hostname).rstrip('/')


class CheckoutHandoffView(GuestView):
    @extend_schema(request=QuoteSerializer, responses={200:{'type':'object'}})
    def post(self, request):
        ensure_local()
        domain = store_domain(request)
        data = QuoteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        expire_orders()
        quote(domain.business, data.validated_data['items'])
        token = signing.dumps({
            'domain':domain.pk, 'business':str(domain.business_id), 'key':str(uuid.uuid4()),
            'items':[{'variant_id':str(row['variant_id']),'quantity':row['quantity']} for row in data.validated_data['items']],
        }, salt=SALT, compress=True)
        return Response({'payment_url':settings.PAYMENT_PUBLIC_URL+'/?checkout='+token})


class HandoffInput(serializers.Serializer):
    token = serializers.CharField(max_length=16000)
    details = serializers.DictField(required=False)


class PaymentCheckoutView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(request=HandoffInput, responses={200:{'type':'object'},201:{'type':'object'}})
    def post(self, request):
        # Only the payments service can exchange a signed cart or submit its order.
        verify_request(request)
        data = HandoffInput(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            handoff = signing.loads(data.validated_data['token'], salt=SALT, max_age=3600)
        except signing.BadSignature:
            raise ValidationError('This checkout link has expired or is invalid. Return to your shop cart to open a new checkout.')
        domain = get_object_or_404(Domain.objects.select_related('business__store_settings'), pk=handoff['domain'], business_id=handoff['business'], verified=True, business__published=True, business__suspended=False, business__provisioning_status='ready')
        items = QuoteSerializer(data={'items':handoff['items']})
        items.is_valid(raise_exception=True)
        expire_orders()
        if 'details' in data.validated_data:
            # Store/cart/idempotency identity can never be replaced by browser input.
            checkout = CheckoutSerializer(data={**data.validated_data['details'], 'items':handoff['items'], 'checkout_key':handoff['key']})
            checkout.is_valid(raise_exception=True)
            result = create_checkout(domain, checkout.validated_data, order_id=uuid.UUID(handoff['key']))
            if result.status_code == 201:
                result.data['return_url'] = store_url(domain)+'/checkout?order='+result.data['token']
            return result
        existing = Order.objects.filter(business=domain.business, checkout_key=handoff['key']).first()
        if existing:
            return Response({'order':order_data(existing),'return_url':store_url(domain)+'/checkout?order='+existing.token})
        totals, _ = quote(domain.business, items.validated_data['items'])
        return Response({'business_id':str(domain.business_id),'order_number':handoff['key'][:8].upper(),'store_name':domain.business.name,'return_url':store_url(domain)+'/#products', **totals})
