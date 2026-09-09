"""Versioned, encrypted merchant credentials. Existing payments retain their configuration."""
import json

from apps.checkout.protocol import verify_request
from cryptography.fernet import Fernet
from django.conf import settings
from django.db import transaction
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PaymentConfiguration

SECRET_FIELDS = {'secret_key', 'webhook_secret', 'api_token', 'callback_secret'}


def latest(business_id, provider):
    return PaymentConfiguration.objects.filter(business_id=business_id, provider=provider).first()


def unpack(record):
    return json.loads(Fernet(settings.ENCRYPTION_KEY.encode()).decrypt(record.encrypted_values.encode()))


def defaults(provider):
    if provider == 'stripe':
        return {'enabled': False, 'secret_key': '', 'webhook_secret': ''}
    return {'enabled': False, 'tenant_id': '', 'api_token': '', 'use_default_config': False,
            'callback_secret': '', 'callback_url': ''}


def platform_values(provider):
    if provider == 'stripe':
        return {'enabled': True, 'secret_key': settings.STRIPE_SECRET_KEY,
                'webhook_secret': settings.STRIPE_WEBHOOK_SECRET}
    return {'enabled': settings.VENTY_MPESA_ENABLED, 'tenant_id': settings.VENTY_MPESA_TENANT_ID,
            'api_token': settings.VENTY_MPESA_API_TOKEN, 'callback_secret': settings.VENTY_MPESA_CALLBACK_SECRET,
            'callback_url': settings.VENTY_MPESA_CALLBACK_URL,
            'use_default_config': settings.VENTY_MPESA_USE_DEFAULT_CONFIG}


def stored_values(business_id, provider):
    record = latest(business_id, provider)
    return unpack(record) if record else {'enabled': True, 'use_platform_defaults': True}


def values(provider, business_id=None, configuration=None):
    if configuration:
        stored = unpack(configuration)
    elif business_id:
        stored = stored_values(business_id, provider)
    else:
        return platform_values(provider)
    if stored.get('use_platform_defaults', False):
        shared = platform_values(provider)
        return {**shared, 'enabled': stored['enabled'] and shared['enabled']}
    return stored


def encrypt_values(config):
    return Fernet(settings.ENCRYPTION_KEY.encode()).encrypt(json.dumps(config).encode()).decode()


def for_session(session):
    if session.encrypted_credentials:
        return json.loads(Fernet(settings.ENCRYPTION_KEY.encode()).decrypt(session.encrypted_credentials.encode()))
    # Preserve pre-existing sessions. New sessions always snapshot the effective
    # credentials, so switching accounts or rotating defaults cannot reroute them.
    if session.business_id and not session.configuration_id:
        return defaults(session.provider)
    return values(session.provider, configuration=session.configuration)


def credentials_ready(provider, config):
    return bool(config['enabled'] and (config['secret_key'].startswith('sk_test_')
                if provider == 'stripe' else config['tenant_id']))


def public_values(business_id, provider):
    stored = stored_values(business_id, provider)
    shared = stored.get('use_platform_defaults', False)
    # Never serialize platform tenant IDs, callback URLs, tokens, or saved-secret
    # indicators as merchant fields. The browser receives only mode/readiness.
    visible = defaults(provider) if shared else stored
    public = {key + '_saved' if key in SECRET_FIELDS else key:
              bool(value) if key in SECRET_FIELDS else value for key, value in visible.items()}
    return {**public, 'enabled': stored['enabled'], 'use_platform_defaults': shared,
            'source': 'mshoppa' if shared else 'store',
            'ready': credentials_ready(provider, values(provider, business_id))}


class ConfigurationInput(serializers.Serializer):
    business_id = serializers.UUIDField()
    provider = serializers.ChoiceField(choices=['stripe', 'mpesa'], required=False)
    values = serializers.DictField(required=False)


class SourceInput(serializers.Serializer):
    enabled = serializers.BooleanField()
    use_platform_defaults = serializers.BooleanField(default=False)


class StripeInput(SourceInput):
    secret_key = serializers.RegexField(r'^sk_test_[A-Za-z0-9_]+$', max_length=300, required=False, allow_blank=True, trim_whitespace=True)
    webhook_secret = serializers.RegexField(r'^whsec_[A-Za-z0-9_]+$', max_length=300, required=False, allow_blank=True, trim_whitespace=True)


class MpesaInput(SourceInput):
    tenant_id = serializers.RegexField(r'^[A-Za-z0-9_-]+$', max_length=100, allow_blank=True)
    api_token = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    use_default_config = serializers.BooleanField()
    callback_url = serializers.URLField(max_length=500, allow_blank=True)
    callback_secret = serializers.CharField(max_length=300, required=False, allow_blank=True)

    def validate_callback_url(self, value):
        if value and not value.startswith('https://'):
            raise serializers.ValidationError('Use an HTTPS callback URL.')
        return value


class ConfigurationView(APIView):
    @transaction.atomic
    def post(self, request):
        verify_request(request)
        data = ConfigurationInput(data=request.data)
        data.is_valid(raise_exception=True)
        payload = data.validated_data
        business_id = payload['business_id']
        if 'values' in payload:
            provider = payload.get('provider')
            if not provider:
                raise serializers.ValidationError('Choose a payment provider.')
            source = SourceInput(data=payload['values'])
            source.is_valid(raise_exception=True)
            if source.validated_data['use_platform_defaults']:
                config = dict(source.validated_data)
            else:
                schema = StripeInput if provider == 'stripe' else MpesaInput
                submitted = schema(data=payload['values'])
                submitted.is_valid(raise_exception=True)
                stored = stored_values(business_id, provider)
                # An override starts empty; never merge another account's credentials.
                config = defaults(provider) if stored.get('use_platform_defaults', False) else stored
                for key, value in submitted.validated_data.items():
                    if key not in SECRET_FIELDS or value:
                        config[key] = value
                if config['enabled']:
                    if provider == 'stripe' and not config['secret_key']:
                        raise serializers.ValidationError({'secret_key': 'Enter your Stripe test secret key.'})
                    if provider == 'mpesa' and not config['tenant_id']:
                        raise serializers.ValidationError({'tenant_id': 'Enter your Venty tenant ID.'})
                    if provider == 'mpesa' and config['callback_url'] and not config['callback_secret']:
                        raise serializers.ValidationError({'callback_secret': 'Set a secret to verify callbacks.'})
            PaymentConfiguration.objects.create(business_id=business_id, provider=provider, encrypted_values=encrypt_values(config))
        return Response({provider: public_values(business_id, provider) for provider in ['stripe', 'mpesa']})
