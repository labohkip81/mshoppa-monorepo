from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient


@override_settings(DEBUG=True, LOCAL_DUMMY_PAYMENTS=True)
class CheckoutBridgeTests(TestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)

    @patch('simulator.checkout_views.signed_post')
    def test_preview_and_submission_use_core_and_require_csrf(self, core):
        core.return_value = {'store_name':'Test shop','methods':['stripe','mpesa']}
        preview = self.client.get('/api/checkout/?token=signed-cart')
        self.assertEqual(preview.status_code,200)
        self.assertIn('providers',preview.data)
        self.assertEqual(core.call_args.args[1],{'token':'signed-cart'})
        payload = {'token':'signed-cart','details':{'name':'Buyer','provider':'stripe'}}
        self.assertEqual(self.client.post('/api/checkout/',payload,format='json').status_code,403)
        csrf=self.client.get('/api/auth/csrf/').json()['token']
        core.return_value={'payment_url':'http://localhost:4204/?session=fixture'}
        self.assertEqual(self.client.post('/api/checkout/',payload,format='json',HTTP_X_CSRFTOKEN=csrf).status_code,200)
        self.assertEqual(core.call_args.args[1],payload)

    @patch('simulator.checkout_views.signed_post',side_effect=OSError)
    def test_outage_is_retryable(self,core):
        self.assertEqual(self.client.get('/api/checkout/?token=signed-cart').status_code,503)
        self.assertEqual(self.client.get('/api/checkout/').status_code,400)
