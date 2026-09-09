"""Local HTTP integration test; creates only an isolated, subsequently offline test store."""

import json
import uuid
from http.cookies import SimpleCookie
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from django.core.management.base import BaseCommand

from apps.businesses.models import Business, Domain, StoreSettings
from apps.catalog.models import Product, Variant
from apps.checkout.models import Order
from apps.checkout.protocol import ensure_local


class Command(BaseCommand):
    help = (
        "Test local core/payment HTTP flows with isolated test data. Both services must be running."
    )

    def handle(self, *args, **options):
        ensure_local()
        suffix = uuid.uuid4().hex[:10]
        business = Business.objects.create(
            name="Checkout HTTP test",
            slug=f"checkout-test-{suffix}",
            country="KE",
            currency="KES",
            provisioning_status="ready",
            published=True,
        )
        StoreSettings.objects.create(business=business, tax_rate="16")
        hostname = business.slug + ".localhost"
        Domain.objects.create(business=business, hostname=hostname, verified=True)
        product = Product.objects.create(
            business=business, name="HTTP test tote", slug="http-test-tote", status="published"
        )
        variant = Variant.objects.create(
            product=product, sku="HTTP-TEST", price="100", offer_price="80", stock=10
        )
        jars = {}

        def call(port, host, path, body=None, expected=200):
            cookies = jars.setdefault(host, {})
            headers = {
                "Host": host,
                "Origin": f"http://{host}",
                "Cookie": "; ".join(f"{key}={value}" for key, value in cookies.items()),
            }
            if body is not None:
                token = call(port, host, "/api/auth/csrf/")["token"]
                headers["Cookie"] = "; ".join(f"{key}={value}" for key, value in cookies.items())
                headers.update({"Content-Type": "application/json", "X-CSRFToken": token})
            request = Request(
                f"http://127.0.0.1:{port}{path}",
                data=json.dumps(body).encode() if body is not None else None,
                headers=headers,
            )
            try:
                response = urlopen(request, timeout=15)
            except HTTPError as error:
                response = error
            with response:
                for cookie in response.headers.get_all("Set-Cookie", []):
                    parsed = SimpleCookie()
                    parsed.load(cookie)
                    cookies.update({key: value.value for key, value in parsed.items()})
                result = json.loads(response.read())
                assert response.status == expected, (path, response.status, result)
                return result

        try:
            for provider in ["stripe", "mpesa"]:
                for outcome in ["succeeded", "failed"]:
                    items = [{"variant_id": str(variant.pk), "quantity": 1}]
                    quote = call(8000, hostname + ":4203", "/api/cart/quote/", {"items": items})
                    assert quote["total"] == "92.80", quote
                    payload = {
                        "items": items,
                        "quote_token": quote["quote_token"],
                        "checkout_key": str(uuid.uuid4()),
                        "name": "HTTP Test",
                        "email": "checkout-test@example.test",
                        "address": "Local test only",
                        "provider": provider,
                    }
                    order = call(8000, hostname + ":4203", "/api/checkout/", payload, 201)
                    assert (
                        call(8000, hostname + ":4203", "/api/checkout/", payload, 201)["id"]
                        == order["id"]
                    )
                    session_token = order["payment_url"].split("session=", 1)[1]
                    session = call(
                        8001, "payments.localhost:4204", f"/api/sessions/{session_token}/"
                    )
                    assert session["provider"] == provider and session["amount"] == "92.80"
                    result = call(
                        8001,
                        "payments.localhost:4204",
                        f"/api/sessions/{session_token}/simulate/",
                        {"status": outcome},
                    )
                    expected = "paid" if outcome == "succeeded" else "failed"
                    assert result["order_status"] == expected, result
                    replay = call(
                        8001,
                        "payments.localhost:4204",
                        f"/api/sessions/{session_token}/simulate/",
                        {"status": outcome},
                    )
                    assert replay["order_status"] == expected
                    confirmation = call(8000, hostname + ":4203", f"/api/orders/{order['token']}/")
                    assert confirmation["status"] == expected
            variant.refresh_from_db()
            assert variant.stock == 8
            assert Order.objects.filter(business=business).count() == 4
            self.stdout.write(
                self.style.SUCCESS(
                    "PASS: Stripe/M-Pesa success and failure, server tax totals, checkout idempotency, signed webhook delivery/replay, order confirmation, and stock release."
                )
            )
        finally:
            business.published = False
            business.save(update_fields=["published"])
            product.status = "draft"
            product.save(update_fields=["status"])
            self.stdout.write(
                f"Isolated test store {business.slug} is offline; test orders retained. Existing stores/products were not modified."
            )
