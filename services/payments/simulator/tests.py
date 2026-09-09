import json
import uuid
from datetime import timedelta
from unittest.mock import patch
from urllib.error import URLError

from apps.checkout.protocol import signed_headers
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .models import PaymentSession


@override_settings(DEBUG=True, LOCAL_DUMMY_PAYMENTS=True, STRIPE_PAYMENT_BACKEND="simulator", MPESA_PAYMENT_BACKEND="simulator")
class PaymentTests(TestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)
        self.payload = {
            "order_id": str(uuid.uuid4()),
            "store_name": "Local test",
            "amount": "116.00",
            "currency": "KES",
            "provider": "stripe",
            "expires_at": (timezone.now() + timedelta(minutes=15)).isoformat(),
            "return_url": "http://shop.localhost:4203/checkout?order=opaque-token",
        }

    def signed(self, path, payload):
        body = json.dumps(payload).encode()
        headers = signed_headers(body)
        return self.client.post(
            path,
            body,
            content_type="application/json",
            HTTP_X_MSHOPPA_TIMESTAMP=headers["X-Mshoppa-Timestamp"],
            HTTP_X_MSHOPPA_SIGNATURE=headers["X-Mshoppa-Signature"],
        )

    def create(self):
        response = self.signed("/api/sessions/", self.payload)
        self.assertEqual(response.status_code, 200, response.data)
        return PaymentSession.objects.get()

    def simulate(self, session, status):
        csrf = self.client.get("/api/auth/csrf/").json()["token"]
        return self.client.post(
            f"/api/sessions/{session.token}/simulate/",
            {"status": status},
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )

    def test_signed_creation_idempotency_and_invalid_return_url(self):
        self.assertEqual(
            self.client.post("/api/sessions/", self.payload, format="json").status_code,
            403,
        )
        session = self.create()
        self.assertEqual(self.client.get(f"/api/sessions/{session.token}/").json()["order_number"], str(session.order_id)[:8].upper())
        self.assertEqual(
            self.signed("/api/sessions/", self.payload).json()["session_id"],
            str(session.pk),
        )
        self.assertEqual(PaymentSession.objects.count(), 1)
        self.assertEqual(
            self.signed("/api/sessions/", {**self.payload, "amount": "1"}).status_code,
            400,
        )
        self.assertEqual(
            self.signed(
                "/api/sessions/",
                {**self.payload, "return_url": "https://attacker.example"},
            ).status_code,
            400,
        )

    @patch("simulator.views.signed_post", return_value={"status": "paid"})
    def test_simulated_success_and_replay(self, callback):
        session = self.create()
        self.assertEqual(
            self.client.post(
                f"/api/sessions/{session.token}/simulate/",
                {"status": "succeeded"},
                format="json",
            ).status_code,
            403,
        )
        first = self.simulate(session, "succeeded")
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(first.json()["order_status"], "paid")
        payload = callback.call_args.args[1]
        self.assertEqual(payload["amount"], "116.00")
        self.assertEqual(self.simulate(session, "succeeded").status_code, 200)
        self.assertEqual(callback.call_args.args[1]["event_id"], payload["event_id"])
        self.assertEqual(self.simulate(session, "failed").status_code, 400)

    @patch("simulator.views.signed_post", return_value={"status": "failed"})
    def test_mpesa_webhook_provider_and_signature(self, callback):
        self.payload["provider"] = "mpesa"
        session = self.create()
        event = {
            "session_id": str(session.pk),
            "event_id": str(uuid.uuid4()),
            "status": "failed",
        }
        self.assertEqual(
            self.client.post(
                "/api/webhooks/dummy/mpesa/", event, format="json"
            ).status_code,
            403,
        )
        self.assertEqual(
            self.signed("/api/webhooks/dummy/stripe/", event).status_code, 400
        )
        self.assertEqual(
            self.signed("/api/webhooks/dummy/mpesa/", event).status_code, 200
        )
        self.assertEqual(callback.call_args.args[1]["provider"], "mpesa")

    def test_delivery_failure_is_retryable_and_expired_success_rejected(self):
        session = self.create()
        with patch("simulator.views.signed_post", side_effect=URLError("offline")):
            self.assertEqual(self.simulate(session, "succeeded").status_code, 503)
        session.refresh_from_db()
        event_id = session.event_id
        self.assertFalse(session.delivered)
        with patch(
            "simulator.views.signed_post", return_value={"status": "paid"}
        ) as callback:
            self.assertEqual(self.simulate(session, "succeeded").status_code, 200)
            self.assertEqual(callback.call_args.args[1]["event_id"], str(event_id))
        self.payload["order_id"] = str(uuid.uuid4())
        self.payload["expires_at"] = (timezone.now() - timedelta(minutes=1)).isoformat()
        self.signed("/api/sessions/", self.payload)
        expired = PaymentSession.objects.get(order_id=self.payload["order_id"])
        self.assertEqual(self.simulate(expired, "succeeded").status_code, 400)

    def test_unknown_session_and_disabled_mode(self):
        self.assertEqual(self.client.get("/api/sessions/unknown/").status_code, 404)
        with override_settings(LOCAL_DUMMY_PAYMENTS=False):
            self.assertEqual(
                self.signed("/api/sessions/", self.payload).status_code, 403
            )
