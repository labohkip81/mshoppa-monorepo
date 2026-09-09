import json
from urllib.error import HTTPError

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.checkout.protocol import signed_post

from .management_api import access, audit
from .models import StoreSettings


class PaymentSettingsInput(serializers.Serializer):
    provider = serializers.ChoiceField(choices=['stripe', 'mpesa'])
    values = serializers.DictField()


def payment_service(path, payload):
    try:
        return Response(signed_post(settings.PAYMENT_SERVICE_URL + path, payload))
    except HTTPError as error:
        if error.code == 400:
            try:
                return Response(json.loads(error.read(65536)), status=400)
            except ValueError:
                pass
        return Response({'detail': 'Payment settings are temporarily unavailable.'}, status=503)
    except (OSError, ValueError):
        return Response({'detail': 'Payment settings are temporarily unavailable.'}, status=503)


class PaymentSettingsView(APIView):
    @extend_schema(responses={200: {'type': 'object'}})
    def get(self, request, business_id):
        access(request, business_id, ['owner', 'manager'])
        return payment_service('/api/configuration/', {'business_id': str(business_id)})

    @extend_schema(request=PaymentSettingsInput, responses={200: {'type': 'object'}})
    def patch(self, request, business_id):
        business = access(request, business_id, ['owner'])
        data = PaymentSettingsInput(data=request.data)
        data.is_valid(raise_exception=True)
        response = payment_service('/api/configuration/', {'business_id': str(business_id), **data.validated_data})
        if response.status_code == 200:
            provider = data.validated_data['provider']
            enabled = response.data.get(provider, {}).get('enabled')
            if isinstance(enabled, bool):
                StoreSettings.objects.filter(business=business).update(**{provider + '_enabled': enabled})
            audit(request, business, 'payments.configuration_updated', data.validated_data['provider'])
        return response
