import hashlib
import hmac
import json
import time
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import stripe
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from .models import PaymentSession
from .providers import ProviderUnavailable, StripeAdapter, VentyMpesaAdapter, minor_amount


@override_settings(DEBUG=True, LOCAL_DUMMY_PAYMENTS=True, STRIPE_SECRET_KEY='sk_test_fixture', VENTY_MPESA_ENABLED=True, VENTY_MPESA_TENANT_ID='tenant-fixture', VENTY_MPESA_CALLBACK_SECRET='fixture-callback')
class ProviderTests(TestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)
        self.session = PaymentSession.objects.create(order_id=uuid.uuid4(), store_name='Provider test', amount=Decimal('116'), currency='KES', provider='stripe', backend='stripe', expires_at=timezone.now()+timedelta(minutes=35), return_url='http://shop.localhost:4203/checkout')

    def post(self, action, payload=None):
        token = self.client.get('/api/auth/csrf/').json()['token']
        return self.client.post(f'/api/sessions/{self.session.token}/{action}/', payload or {}, format='json', HTTP_X_CSRFTOKEN=token)

    def mpesa(self):
        self.session.provider = 'mpesa'
        self.session.backend = 'venty'
        self.session.save()

    def stripe_data(self, **changes):
        return {'id': 'cs_test_fixture', 'livemode': False, 'client_reference_id': str(self.session.pk), 'metadata': {'order_id': str(self.session.order_id)}, 'amount_total': 11600, 'currency': 'kes', 'payment_status': 'paid', 'status': 'complete', **changes}

    @patch('simulator.providers.stripe_client')
    def test_stripe_start_idempotency_and_verified_refresh(self, client):
        client.return_value.v1.checkout.sessions.create.return_value = stripe.StripeObject.construct_from(self.stripe_data(url='https://checkout.stripe.com/c/pay/cs_test_fixture'), 'sk_test_fixture')
        self.assertEqual(self.client.post(f'/api/sessions/{self.session.token}/start/', {}, format='json').status_code, 403)
        self.assertEqual(self.post('start').status_code, 200)
        self.assertEqual(self.post('start').status_code, 200)
        create = client.return_value.v1.checkout.sessions.create
        self.assertEqual(create.call_count, 1)
        self.assertEqual(create.call_args.kwargs['options']['idempotency_key'], f'mshoppa-{self.session.pk}')
        self.assertEqual(create.call_args.args[0]['line_items'][0]['price_data']['unit_amount'], 11600)
        client.return_value.v1.checkout.sessions.retrieve.return_value = stripe.StripeObject.construct_from(self.stripe_data(), 'sk_test_fixture')
        with patch('simulator.views.signed_post', return_value={'status':'paid'}) as callback:
            self.assertEqual(self.post('refresh').data['order_status'], 'paid')
            first = callback.call_args.args[1]['event_id']
            self.assertEqual(self.post('refresh').status_code, 200)
            self.assertEqual(callback.call_args.args[1]['event_id'], first)
        self.assertEqual(self.post('simulate', {'status':'succeeded'}).status_code, 400)

    def test_stripe_rejects_wrong_amount_order_currency_and_live_mode(self):
        self.session.external_id = 'cs_test_fixture'
        for changes in [{'amount_total':1}, {'metadata':{'order_id':str(uuid.uuid4())}}, {'currency':'usd'}, {'livemode':True}]:
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                StripeAdapter().verify(self.session, self.stripe_data(**changes))
        self.assertEqual(minor_amount('5', 'UGX'), 500)
        self.assertEqual(minor_amount('5', 'RWF'), 5)
        with override_settings(STRIPE_SECRET_KEY='sk_live_fixture'):
            self.assertEqual(self.post('start').status_code, 400)

    @override_settings(STRIPE_WEBHOOK_SECRET='whsec_fixture')
    def test_stripe_actual_signature_verification_and_replay(self):
        self.session.external_id = 'cs_test_fixture'
        self.session.save()
        event = {'id':'evt_fixture','type':'checkout.session.completed','livemode':False,'data':{'object':self.stripe_data()}}
        body = json.dumps(event).encode()
        stamp = str(int(time.time()))
        digest = hmac.new(b'whsec_fixture', stamp.encode()+b'.'+body, hashlib.sha256).hexdigest()
        with patch('simulator.views.signed_post', return_value={'status':'paid'}) as callback:
            self.assertEqual(self.client.post('/api/webhooks/stripe/', body, content_type='application/json').status_code, 403)
            for _ in range(2):
                response = self.client.post('/api/webhooks/stripe/', body, content_type='application/json', HTTP_STRIPE_SIGNATURE=f't={stamp},v1={digest}')
                self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(callback.call_args_list[0].args[1], callback.call_args_list[1].args[1])

    @patch('simulator.providers.VentyMpesaAdapter.request')
    def test_venty_contract_phone_amount_and_payment_id_lookup(self, request):
        self.mpesa()
        external = str(uuid.uuid4())
        request.return_value = {'is_ok':True, 'payment_id':external}
        result = self.post('start', {'phone':'+254 712 345 678'})
        self.assertEqual(result.status_code, 200, result.data)
        payload = request.call_args.args[1]
        self.assertEqual(payload['amount'], 116)
        self.assertIsInstance(payload['amount'], int)
        self.assertEqual(payload['phone_number'], '254712345678')
        self.assertEqual(payload['transaction_id'], str(self.session.pk))
        self.assertEqual(self.post('start', {'phone':'0712345678'}).status_code, 200)
        self.assertEqual(request.call_count, 1)
        request.return_value = {'id':external, 'transaction_id':str(self.session.pk), 'tenant_id':'tenant-fixture', 'amount':'116.00','phone_number':'254712345678','status':'SUCCEEDED'}
        with patch('simulator.views.signed_post', return_value={'status':'paid'}):
            self.assertEqual(self.post('refresh').data['order_status'], 'paid')
        self.assertEqual(request.call_args.args[0], f'stkpush/payment-detail/{external}/')

    @patch('simulator.providers.VentyMpesaAdapter.request', side_effect=ProviderUnavailable('Uncertain request'))
    def test_venty_timeout_never_sends_second_prompt(self, request):
        self.mpesa()
        self.assertEqual(self.post('start', {'phone':'0712345678'}).status_code, 503)
        self.assertEqual(self.post('start', {'phone':'0712345678'}).status_code, 400)
        self.assertEqual(request.call_count, 1)
        self.session.refresh_from_db()
        self.assertEqual(self.session.initiation_state, 'unknown')

    @patch('simulator.providers.VentyMpesaAdapter.request')
    def test_venty_disabled_and_fractional_total_do_not_call_provider(self, request):
        self.mpesa()
        with override_settings(VENTY_MPESA_ENABLED=False):
            self.assertEqual(self.post('start', {'phone':'0712345678'}).status_code, 400)
        self.session.amount = Decimal('116.01')
        self.session.save()
        self.assertEqual(self.post('start', {'phone':'0712345678'}).status_code, 400)
        request.assert_not_called()

    def test_venty_secret_receipt_and_amount_required(self):
        self.mpesa()
        self.session.initiation_state = 'unknown'
        self.session.save()
        payload = {'order_number':str(self.session.pk), 'amount':'116.00', 'payment_status':'paid', 'mpesa_receipt_number':'FIXTURE123'}
        endpoint = '/api/webhooks/venty/mpesa/'
        self.assertEqual(self.client.post(endpoint,payload,format='json').status_code,403)
        for changes in [{'amount':'1'}, {'mpesa_receipt_number':''}]:
            self.assertEqual(self.client.post(endpoint,{**payload,**changes},format='json',HTTP_X_PAYMENT_CALLBACK_SECRET='fixture-callback').status_code,400)
        with patch('simulator.views.signed_post',return_value={'status':'paid'}):
            self.assertEqual(self.client.post(endpoint,payload,format='json',HTTP_X_PAYMENT_CALLBACK_SECRET='fixture-callback').status_code,200)
        self.session.refresh_from_db()
        self.assertEqual(self.session.receipt_number, 'FIXTURE123')

    @patch('simulator.providers.VentyMpesaAdapter.request')
    def test_venty_status_must_match_tenant_and_order(self, request):
        self.mpesa()
        self.session.external_id = str(uuid.uuid4())
        self.session.phone = '254712345678'
        data={'id':self.session.external_id,'transaction_id':str(self.session.pk),'tenant_id':'tenant-fixture','amount':'116.00','phone_number':self.session.phone,'status':'SUCCEEDED'}
        for changes in [{'tenant_id':'other'}, {'transaction_id':str(uuid.uuid4())}, {'amount':'1'}]:
            request.return_value = {**data,**changes}
            with self.assertRaises(ValidationError):
                VentyMpesaAdapter().status(self.session)
