import json
import uuid
from datetime import timedelta
from unittest.mock import patch

from apps.checkout.protocol import signed_headers
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .configuration import for_session, latest, values
from .models import PaymentSession
from .providers import VentyMpesaAdapter, provider_config


@override_settings(DEBUG=True, LOCAL_DUMMY_PAYMENTS=True)
class ConfigurationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.business = uuid.uuid4()

    def post(self, path, payload):
        body = json.dumps(payload).encode()
        headers = {'HTTP_' + k.upper().replace('-', '_'): v for k, v in signed_headers(body).items() if k != 'Content-Type'}
        return self.client.post(path, body, content_type='application/json', **headers)

    def configure(self, provider='stripe', config=None, business=None):
        return self.post('/api/configuration/', {'business_id': str(business or self.business), 'provider': provider, 'values': config or {'enabled': True, 'secret_key': 'sk_test_fixture'}})

    def test_signed_access_encryption_redaction_and_store_isolation(self):
        self.assertEqual(self.client.post('/api/configuration/', {}, format='json').status_code, 403)
        result = self.configure()
        self.assertEqual(result.status_code, 200, result.data)
        self.assertTrue(result.data['stripe']['secret_key_saved'])
        self.assertNotIn('sk_test_fixture', json.dumps(result.data))
        self.assertNotIn('sk_test_fixture', latest(self.business, 'stripe').encrypted_values)
        self.assertEqual(values('stripe', self.business)['secret_key'], 'sk_test_fixture')
        other = uuid.uuid4()
        self.assertFalse(provider_config(other)['stripe']['ready'])
        self.assertTrue(provider_config(self.business)['stripe']['ready'])

    def test_empty_secrets_preserve_configuration_and_live_keys_are_rejected(self):
        self.configure()
        self.assertEqual(self.configure(config={'enabled': True, 'secret_key': ''}).status_code, 200)
        self.assertEqual(values('stripe', self.business)['secret_key'], 'sk_test_fixture')
        self.assertEqual(self.configure(config={'enabled': True, 'secret_key': 'sk_live_fixture'}).status_code, 400)
        self.assertEqual(self.configure(config={'enabled': False}).status_code, 200)
        self.assertFalse(provider_config(self.business)['stripe']['ready'])

    def test_sessions_pin_configuration_during_key_rotation(self):
        self.configure()
        data = {'order_id': str(uuid.uuid4()), 'business_id': str(self.business), 'store_name': 'Shop', 'amount': '100.00', 'currency': 'KES', 'provider': 'stripe', 'expires_at': (timezone.now()+timedelta(minutes=35)).isoformat(), 'return_url': 'http://shop.localhost:4203/checkout'}
        result = self.post('/api/sessions/', data)
        self.assertEqual(result.status_code, 200, result.data)
        session = PaymentSession.objects.get(pk=result.data['session_id'])
        self.configure(config={'enabled': True, 'secret_key': 'sk_test_rotated'})
        self.assertEqual(for_session(session)['secret_key'], 'sk_test_fixture')
        self.assertEqual(values('stripe', self.business)['secret_key'], 'sk_test_rotated')
        self.assertEqual(self.post('/api/sessions/', data).data['session_id'], str(session.pk))
        data['business_id'] = str(uuid.uuid4())
        self.assertEqual(self.post('/api/sessions/', data).status_code, 400)

    @patch('simulator.providers.VentyMpesaAdapter.request')
    def test_mpesa_uses_merchant_tenant(self, request):
        config = {'enabled': True, 'tenant_id': 'store-one', 'use_default_config': False, 'callback_url': ''}
        self.assertEqual(self.configure('mpesa', config).status_code, 200)
        session = PaymentSession.objects.create(business_id=self.business, configuration=latest(self.business, 'mpesa'), order_id=uuid.uuid4(), store_name='Shop', amount='100', currency='KES', provider='mpesa', backend='venty', expires_at=timezone.now()+timedelta(minutes=35))
        session.refresh_from_db()
        request.return_value = {'is_ok': True, 'payment_id': str(uuid.uuid4())}
        VentyMpesaAdapter().start(session, '0712345678')
        self.assertEqual(request.call_args.args[1]['tenant_id'], 'store-one')
        config['callback_url'] = 'http://example.test/callback'
        self.assertEqual(self.configure('mpesa', config).status_code, 400)

    @patch('simulator.providers.stripe.StripeClient')
    def test_stripe_adapter_uses_the_saved_store_key(self, client):
        from .providers import StripeAdapter
        self.configure()
        session = PaymentSession.objects.create(business_id=self.business, configuration=latest(self.business, 'stripe'), order_id=uuid.uuid4(), store_name='Shop', amount='100', currency='KES', provider='stripe', backend='stripe', expires_at=timezone.now()+timedelta(minutes=35))
        session.refresh_from_db()
        StripeAdapter().validate(session)
        client.assert_called_once_with('sk_test_fixture')

    @override_settings(STRIPE_SECRET_KEY='sk_test_shared', STRIPE_WEBHOOK_SECRET='whsec_shared', VENTY_MPESA_ENABLED=True, VENTY_MPESA_TENANT_ID='shared-tenant', VENTY_MPESA_API_TOKEN='shared-token', VENTY_MPESA_CALLBACK_SECRET='shared-callback', VENTY_MPESA_CALLBACK_URL='https://private.example.test/callback', VENTY_MPESA_USE_DEFAULT_CONFIG=True)
    def test_shared_accounts_are_ready_without_exposing_configuration(self):
        result = self.post('/api/configuration/', {'business_id': str(self.business)})
        self.assertEqual(result.status_code, 200)
        for provider in ['stripe', 'mpesa']:
            self.assertTrue(result.data[provider]['use_platform_defaults'])
            self.assertTrue(result.data[provider]['ready'])
            self.assertEqual(result.data[provider]['source'], 'mshoppa')
            self.assertTrue(provider_config(self.business)[provider]['ready'])
        for private in ['sk_test_shared', 'whsec_shared', 'shared-tenant', 'shared-token', 'shared-callback', 'private.example.test']:
            self.assertNotIn(private, json.dumps(result.data))
        self.assertFalse(result.data['stripe']['secret_key_saved'])
        self.assertEqual(result.data['mpesa']['tenant_id'], '')
        self.assertEqual(result.data['mpesa']['callback_url'], '')
        self.assertEqual(values('mpesa', self.business)['tenant_id'], 'shared-tenant')

    @override_settings(STRIPE_SECRET_KEY='sk_test_shared', STRIPE_WEBHOOK_SECRET='whsec_shared')
    def test_overrides_never_copy_shared_secrets_and_can_restore_defaults(self):
        self.assertEqual(self.configure(config={'enabled': True, 'use_platform_defaults': False, 'secret_key': ''}).status_code, 400)
        self.assertEqual(self.configure().status_code, 200)
        self.assertEqual(values('stripe', self.business)['webhook_secret'], '')
        result = self.configure(config={'enabled': True, 'use_platform_defaults': True, 'secret_key': 'sk_test_ignored'})
        self.assertTrue(result.data['stripe']['ready'])
        self.assertFalse(result.data['stripe']['secret_key_saved'])
        self.assertEqual(values('stripe', self.business)['secret_key'], 'sk_test_shared')
        self.assertEqual(self.configure(config={'enabled': True, 'secret_key': ''}).status_code, 400)
        result = self.configure(config={'enabled': False, 'use_platform_defaults': True})
        self.assertFalse(result.data['stripe']['ready'])
        self.assertFalse(provider_config(self.business)['stripe']['ready'])
        self.assertTrue(provider_config(uuid.uuid4())['stripe']['ready'])

    @override_settings(STRIPE_SECRET_KEY='sk_test_shared')
    def test_shared_session_keeps_account_after_rotation_and_store_override(self):
        from .views import session_data
        payload = {'order_id': str(uuid.uuid4()), 'business_id': str(self.business), 'store_name': 'Shop', 'amount': '100.00', 'currency': 'KES', 'provider': 'stripe', 'expires_at': (timezone.now()+timedelta(minutes=35)).isoformat(), 'return_url': 'http://shop.localhost:4203/checkout'}
        result = self.post('/api/sessions/', payload)
        self.assertEqual(result.status_code, 200, result.data)
        session = PaymentSession.objects.get(pk=result.data['session_id'])
        self.assertNotIn('sk_test_shared', session.encrypted_credentials)
        self.assertNotIn('sk_test_shared', json.dumps(session_data(session)))
        with override_settings(STRIPE_SECRET_KEY='sk_test_rotated'):
            self.assertEqual(values('stripe', self.business)['secret_key'], 'sk_test_rotated')
            self.configure()
            self.assertEqual(for_session(session)['secret_key'], 'sk_test_shared')
            self.assertEqual(self.post('/api/sessions/', payload).data['session_id'], str(session.pk))
            session.refresh_from_db()
            self.assertEqual(for_session(session)['secret_key'], 'sk_test_shared')

    @override_settings(VENTY_MPESA_ENABLED=True, VENTY_MPESA_TENANT_ID='default', VENTY_MPESA_USE_DEFAULT_CONFIG=True)
    @patch('simulator.providers.VentyMpesaAdapter.request')
    def test_shared_venty_uses_default_remote_account(self, request):
        payload = {'order_id': str(uuid.uuid4()), 'business_id': str(self.business), 'store_name': 'Shop', 'amount': '100.00', 'currency': 'KES', 'provider': 'mpesa', 'expires_at': (timezone.now()+timedelta(minutes=35)).isoformat(), 'return_url': 'http://shop.localhost:4203/checkout'}
        result = self.post('/api/sessions/', payload)
        session = PaymentSession.objects.get(pk=result.data['session_id'])
        request.return_value = {'is_ok': True, 'payment_id': str(uuid.uuid4())}
        VentyMpesaAdapter().start(session, '0712345678')
        self.assertEqual(request.call_args.args[1]['tenant_id'], 'default')
        self.assertTrue(request.call_args.args[1]['use_default_config'])
        self.assertEqual(self.configure('mpesa', {'enabled': True, 'use_platform_defaults': False, 'tenant_id': '', 'use_default_config': False, 'callback_url': ''}).status_code, 400)
