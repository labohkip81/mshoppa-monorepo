"""Same-origin checkout bridge; core remains authoritative for cart and order data."""
import json
from urllib.error import HTTPError

from apps.checkout.protocol import ensure_local, signed_post
from django.conf import settings
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView

from .providers import provider_config


class CheckoutView(APIView):
    def exchange(self, token, details=None):
        ensure_local()
        if not isinstance(token,str) or not token or len(token) > 16000:
            return Response({'detail':'Open checkout from your shop cart.'}, status=400)
        payload = {'token':token}
        if details is not None:
            payload['details'] = details
        try:
            result = signed_post(settings.CORE_CHECKOUT_URL, payload)
        except HTTPError as error:
            if error.code in {400,403,404}:
                try:
                    return Response(json.loads(error.read(65536)), status=error.code)
                except ValueError:
                    pass
            return Response({'detail':'Checkout is temporarily unavailable. Try again.'},status=503)
        except (OSError, ValueError):
            return Response({'detail':'Checkout is temporarily unavailable. Try again.'},status=503)
        if 'methods' in result:
            config = provider_config(result.pop("business_id", None))
            result['providers'] = {method:config[method] for method in result['methods']}
        return Response(result)

    def get(self, request):
        return self.exchange(request.query_params.get('token',''))

    def post(self, request):
        SessionAuthentication().enforce_csrf(request)
        if not isinstance(request.data, dict) or not isinstance(request.data.get('details'), dict):
            return Response({'detail':'Enter your order details.'},status=400)
        return self.exchange(request.data.get('token',''), request.data['details'])
