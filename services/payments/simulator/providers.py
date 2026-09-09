"""Provider adapters. Credentials stay in the payments service."""

import json
import re
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import stripe
from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .configuration import for_session, values


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ProviderUnavailable(Exception):
    pass


def stripe_client(config=None):
    config = config if config is not None else values("stripe")
    key = config["secret_key"] if config["enabled"] else ""
    if not key.startswith("sk_test_"):
        raise ValidationError(
            "Configure a Stripe test secret key in the payments service. Live Stripe keys are not accepted."
        )
    return stripe.StripeClient(key)


def provider_config(business_id=None):
    stripe_config, mpesa_config = values('stripe', business_id), values('mpesa', business_id)
    return {
        'stripe': {'backend': settings.STRIPE_PAYMENT_BACKEND,
                   'ready': settings.STRIPE_PAYMENT_BACKEND == 'simulator' or bool(stripe_config['enabled'] and stripe_config['secret_key'].startswith('sk_test_')),
                   'mode': 'test'},
        'mpesa': {'backend': settings.MPESA_PAYMENT_BACKEND,
                  'ready': settings.MPESA_PAYMENT_BACKEND == 'simulator' or bool(mpesa_config['enabled'] and mpesa_config['tenant_id']),
                  'mode': 'simulator' if settings.MPESA_PAYMENT_BACKEND == 'simulator' else 'live'},
    }


def minor_amount(amount, currency):
    # These are the currencies exposed by the existing store application.
    factor = 1 if currency.upper() in {"RWF"} else 100
    return int(Decimal(amount) * factor)


class StripeAdapter:
    def validate(self, session):
        stripe_client(for_session(session))
        if (session.expires_at - timezone.now()).total_seconds() < 1805:
            raise ValidationError(
                "This checkout is too close to expiry. Return to the shop and start a new checkout."
            )
        if (
            session.currency in {"UGX", "RWF"}
            and session.amount != session.amount.to_integral_value()
        ):
            raise ValidationError("This currency requires a whole-unit total.")
        if session.amount <= 0:
            raise ValidationError("Stripe checkout requires a positive amount.")

    def start(self, session, phone=""):
        self.validate(session)
        try:
            result = stripe_client(for_session(session)).v1.checkout.sessions.create(
                {
                    "mode": "payment",
                    "payment_method_types": ["card"],
                    "client_reference_id": str(session.pk),
                    "metadata": {
                        "mshoppa_session_id": str(session.pk),
                        "order_id": str(session.order_id),
                    },
                    "line_items": [
                        {
                            "quantity": 1,
                            "price_data": {
                                "currency": session.currency.lower(),
                                "unit_amount": minor_amount(session.amount, session.currency),
                                "product_data": {"name": f"{session.store_name} order"},
                            },
                        }
                    ],
                    "success_url": settings.PAYMENT_PUBLIC_URL
                    + "/?session="
                    + session.token
                    + "&returned=1",
                    "cancel_url": settings.PAYMENT_PUBLIC_URL + "/?session=" + session.token,
                    "expires_at": int(session.expires_at.timestamp()),
                },
                options={"idempotency_key": f"mshoppa-{session.pk}"},
            )
        except stripe.StripeError:
            raise ProviderUnavailable("Stripe could not start checkout. You can retry safely.")
        result = result.to_dict() if isinstance(result, stripe.StripeObject) else result
        if result.get("livemode") is not False or not str(result.get("url", "")).startswith(
            "https://checkout.stripe.com/"
        ):
            raise ProviderUnavailable("Stripe did not return a valid test checkout.")
        return {"external_id": result["id"], "redirect_url": result["url"]}

    def status(self, session):
        try:
            result = stripe_client(for_session(session)).v1.checkout.sessions.retrieve(session.external_id)
        except stripe.StripeError:
            raise ProviderUnavailable("Stripe status is temporarily unavailable.")
        return self.verify(session, result)

    def verify(self, session, data):
        data = data.to_dict() if isinstance(data, stripe.StripeObject) else data
        if (
            data.get("livemode") is not False
            or data.get("id") != session.external_id
            or data.get("client_reference_id") != str(session.pk)
            or data.get("metadata", {}).get("order_id") != str(session.order_id)
            or data.get("currency", "").upper() != session.currency
            or data.get("amount_total") != minor_amount(session.amount, session.currency)
        ):
            raise ValidationError("Stripe payment does not match this checkout.")
        if data.get("payment_status") == "paid":
            return "succeeded"
        if data.get("status") == "expired":
            return "failed"
        return "pending"


class VentyMpesaAdapter:
    """Contract from Dev/Venty/mpesa-api/stkpush; no tenant-management calls."""

    def __init__(self):
        self.config = values("mpesa")

    def request(self, path, payload=None):
        base = settings.VENTY_MPESA_BASE_URL.rstrip("/")
        parsed = urlsplit(base)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "mpesa.venti.africa"
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
        ):
            raise ValidationError("Use the configured HTTPS Venty M-Pesa service.")
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.config["api_token"]:
            headers["Authorization"] = "Bearer " + self.config["api_token"]
        try:
            with build_opener(NoRedirect()).open(
                Request(
                    base + "/" + path, data=body, headers=headers, method="POST" if body else "GET"
                ),
                timeout=12,
            ) as response:
                return json.loads(response.read(1024 * 1024))
        except (HTTPError, URLError, TimeoutError, OSError, ValueError):
            raise ProviderUnavailable(
                "The M-Pesa service could not confirm this request. Check payment status before starting another checkout."
            )

    def phone(self, value):
        number = re.sub(r"[\s()+-]", "", value)
        if re.fullmatch(r"0[17]\d{8}", number):
            number = "254" + number[1:]
        if not re.fullmatch(r"254[17]\d{8}", number):
            raise ValidationError(
                {"phone": "Enter a Kenyan mobile number, for example 0712345678 or +254712345678."}
            )
        return number

    def validate(self, session):
        self.config = for_session(session)
        if not self.config["enabled"] or not self.config["tenant_id"]:
            raise ValidationError(
                "Venty M-Pesa is not configured yet. Set the tenant and enable the integration in the payments service."
            )
        if (
            session.currency != "KES"
            or session.amount <= 0
            or session.amount != session.amount.to_integral_value()
        ):
            raise ValidationError(
                "M-Pesa requires a positive, whole-shilling KES total. This service does not round or change your order amount."
            )
        if session.expires_at <= timezone.now():
            raise ValidationError("This checkout has expired.")

    def start(self, session, phone):
        self.validate(session)
        payload = {
            "phone_number": self.phone(phone),
            "transaction_id": str(session.pk),
            "tenant_id": self.config["tenant_id"],
            "amount": int(session.amount),
            "payment_type": "mshoppa_order",
            "use_default_config": self.config["use_default_config"],
        }
        if self.config["callback_url"]:
            payload["system_callback_url"] = self.config["callback_url"]
        result = self.request("stkpush/initiate/", payload)
        if result.get("is_ok") is not True or not result.get("payment_id"):
            raise ProviderUnavailable(
                "M-Pesa did not confirm an STK request. Do not retry this checkout until its status is known."
            )
        import uuid

        try:
            external_id = str(uuid.UUID(str(result["payment_id"])))
        except (ValueError, TypeError):
            raise ProviderUnavailable("The M-Pesa service returned an invalid payment reference.")
        return {"external_id": external_id, "redirect_url": ""}

    def status(self, session):
        self.validate_configuration(session)
        result = self.request(f"stkpush/payment-detail/{session.external_id}/")
        try:
            matches = (
                str(result.get("id")) == session.external_id
                and result.get("transaction_id") == str(session.pk)
                and Decimal(str(result.get("amount"))) == session.amount
                and str(result.get("tenant_id")) == self.config["tenant_id"]
                and self.phone(str(result.get("phone_number"))) == session.phone
            )
        except (ValueError, TypeError, ArithmeticError):
            matches = False
        if not matches:
            raise ValidationError("M-Pesa payment does not match this checkout.")
        return {"SUCCEEDED": "succeeded", "FAILED": "failed", "INITIATED": "pending"}.get(
            result.get("status"), "pending"
        )

    def validate_configuration(self, session):
        self.config = for_session(session)
        if not self.config["enabled"] or not self.config["tenant_id"]:
            raise ValidationError("Venty M-Pesa is not configured.")


def adapter(session):
    if session.backend == "stripe":
        return StripeAdapter()
    if session.backend == "venty":
        return VentyMpesaAdapter()
    raise ValidationError("This session uses the local simulator.")
