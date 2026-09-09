# ruff: noqa: F811
import json
import uuid
from datetime import timedelta
from decimal import Decimal
from urllib.error import URLError

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.models import Product, Variant
from apps.checkout.models import Order, PaymentEvent
from apps.checkout.protocol import signed_headers
from apps.checkout.views import expire_orders
from tests.test_foundation import (  # noqa: F401
    application,
    business,
    client,
    login,
    mutate,
    owner,
    reset_throttles,
    staff,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def local_mode(settings):
    settings.DEBUG = True
    settings.LOCAL_DUMMY_PAYMENTS = True


@pytest.fixture
def item(business):
    product = Product.objects.create(
        business=business, name="Tote", slug="tote", status="published"
    )
    return Variant.objects.create(
        product=product, sku="TOTE", price="100", offer_price="80", stock=10
    )


def post(client, business, path, data):
    host = business.domains.get().hostname
    csrf = client.get("/api/auth/csrf/", HTTP_HOST=host).json()["token"]
    return client.post(path, data, format="json", HTTP_HOST=host, HTTP_X_CSRFTOKEN=csrf)


def checkout_data(client, business, item, provider="stripe"):
    items = [{"variant_id": str(item.pk), "quantity": 2}]
    quote = post(client, business, "/api/cart/quote/", {"items": items})
    assert quote.status_code == 200, quote.data
    return {
        "items": items,
        "quote_token": quote.json()["quote_token"],
        "checkout_key": str(uuid.uuid4()),
        "name": "Test Buyer",
        "email": "buyer@example.test",
        "address": "Nairobi",
        "provider": provider,
    }, quote.json()


@pytest.fixture
def simulator(monkeypatch):
    session = str(uuid.uuid4())
    monkeypatch.setattr(
        "apps.checkout.views.signed_post",
        lambda url, payload: {
            "session_id": session,
            "payment_url": "http://payments.localhost:4204/?session=local-test",
        },
    )
    return session


def event(client, order, status="succeeded", **overrides):
    payload = {
        "event_id": str(uuid.uuid4()),
        "order_id": str(order.pk),
        "session_id": order.session_id,
        "status": status,
        "provider": order.provider,
        "amount": str(order.total),
        "currency": order.currency,
        **overrides,
    }
    body = json.dumps(payload).encode()
    headers = signed_headers(body)
    response = client.post(
        "/api/payments/webhooks/dummy/",
        body,
        content_type="application/json",
        HTTP_X_MSHOPPA_TIMESTAMP=headers["X-Mshoppa-Timestamp"],
        HTTP_X_MSHOPPA_SIGNATURE=headers["X-Mshoppa-Signature"],
    )
    return response, payload


@pytest.mark.parametrize("provider", ["stripe", "mpesa"])
def test_tax_checkout_and_verified_success(client, business, item, simulator, provider):
    settings = business.store_settings
    settings.tax_rate = "16"
    settings.save()
    data, quote = checkout_data(client, business, item, provider)
    assert (
        Decimal(quote["subtotal"]) == 160
        and Decimal(quote["tax"]) == Decimal("25.60")
        and Decimal(quote["total"]) == Decimal("185.60")
    )
    first = post(client, business, "/api/checkout/", data)
    assert first.status_code == 201, first.data
    assert post(client, business, "/api/checkout/", data).json()["id"] == first.json()["id"]
    assert Order.objects.count() == 1
    item.refresh_from_db()
    assert item.stock == 8
    order = Order.objects.get()
    result, payload = event(client, order)
    assert result.status_code == 200 and result.json()["status"] == "paid"
    assert event(client, order, **payload)[0].status_code == 200
    assert PaymentEvent.objects.count() == 1
    item.refresh_from_db()
    assert item.stock == 8
    assert event(client, order, status="failed")[0].json()["status"] == "paid"
    item.refresh_from_db()
    assert item.stock == 8


def test_failure_and_expiry_release_stock_once(client, business, item, simulator):
    data, _ = checkout_data(client, business, item)
    post(client, business, "/api/checkout/", data)
    order = Order.objects.get()
    result, payload = event(client, order, status="failed")
    assert result.json()["status"] == "failed"
    event(client, order, **payload)
    item.refresh_from_db()
    assert item.stock == 10
    data, _ = checkout_data(client, business, item)
    post(client, business, "/api/checkout/", data)
    pending = Order.objects.get(status="pending")
    pending.expires_at = timezone.now() - timedelta(seconds=1)
    pending.save()
    expire_orders()
    expire_orders()
    item.refresh_from_db()
    assert item.stock == 10
    assert event(client, pending)[0].json()["status"] == "expired"


def test_tampered_signature_amount_and_reused_event_rejected(client, business, item, simulator):
    data, _ = checkout_data(client, business, item)
    post(client, business, "/api/checkout/", data)
    order = Order.objects.get()
    assert client.post("/api/payments/webhooks/dummy/", {}, format="json").status_code == 403
    assert event(client, order, amount="1")[0].status_code == 400
    assert event(client, order, session_id=str(uuid.uuid4()))[0].status_code == 400
    response, payload = event(client, order)
    assert response.status_code == 200
    assert event(client, order, **{**payload, "status": "failed"})[0].status_code == 400


def test_cart_invalid_unpublished_foreign_inactive_and_quantities(client, business, item):
    for quantity in [0, -1, 100]:
        assert (
            post(
                client,
                business,
                "/api/cart/quote/",
                {"items": [{"variant_id": str(item.pk), "quantity": quantity}]},
            ).status_code
            == 400
        )
    assert (
        post(
            client,
            business,
            "/api/cart/quote/",
            {"items": [{"variant_id": str(uuid.uuid4()), "quantity": 1}]},
        ).status_code
        == 400
    )
    item.is_active = False
    item.save()
    assert (
        post(
            client,
            business,
            "/api/cart/quote/",
            {"items": [{"variant_id": str(item.pk), "quantity": 1}]},
        ).status_code
        == 400
    )
    item.is_active = True
    item.save()
    item.product.status = "draft"
    item.product.save()
    assert (
        post(
            client,
            business,
            "/api/cart/quote/",
            {"items": [{"variant_id": str(item.pk), "quantity": 1}]},
        ).status_code
        == 400
    )


def test_price_changes_overselling_and_disabled_methods(client, business, item, simulator):
    data, _ = checkout_data(client, business, item)
    item.offer_price = "70"
    item.save()
    assert post(client, business, "/api/checkout/", data).status_code == 400
    assert not Order.objects.exists()
    data, _ = checkout_data(client, business, item)
    settings = business.store_settings
    settings.stripe_enabled = False
    settings.save()
    assert post(client, business, "/api/checkout/", data).status_code == 400
    data, _ = checkout_data(client, business, item, "mpesa")
    item.stock = 1
    item.save()
    assert post(client, business, "/api/checkout/", data).status_code == 400
    assert not Order.objects.exists()


def test_stock_reserved_once_on_simulator_outage_and_retry(client, business, item, monkeypatch):
    data, _ = checkout_data(client, business, item)

    def unavailable(*args):
        raise URLError("offline")

    monkeypatch.setattr("apps.checkout.views.signed_post", unavailable)
    assert post(client, business, "/api/checkout/", data).status_code == 503
    assert post(client, business, "/api/checkout/", data).status_code == 503
    item.refresh_from_db()
    assert item.stock == 8 and Order.objects.count() == 1
    monkeypatch.setattr(
        "apps.checkout.views.signed_post",
        lambda *args: {
            "session_id": str(uuid.uuid4()),
            "payment_url": "http://payments.localhost:4204/?session=test",
        },
    )
    assert post(client, business, "/api/checkout/", data).status_code == 201
    item.refresh_from_db()
    assert item.stock == 8
    changed = {**data, "items": [{"variant_id": str(item.pk), "quantity": 1}]}
    assert post(client, business, "/api/checkout/", changed).status_code == 400


def test_checkout_requires_csrf_and_local_mode_and_order_host_scope(
    client, business, item, simulator, settings
):
    data, _ = checkout_data(client, business, item)
    assert (
        client.post(
            "/api/checkout/", data, format="json", HTTP_HOST=business.domains.get().hostname
        ).status_code
        == 403
    )
    result = post(client, business, "/api/checkout/", data).json()
    assert (
        APIClient()
        .get(f"/api/orders/{result['token']}/", HTTP_HOST="unknown.localhost")
        .status_code
        == 404
    )
    settings.LOCAL_DUMMY_PAYMENTS = False
    assert post(client, business, "/api/checkout/", data).status_code == 403


def test_late_provider_success_flags_review_without_reclaiming_stock(client, business, item, simulator):
    data, _ = checkout_data(client, business, item)
    assert post(client, business, '/api/checkout/', data).status_code == 201
    order = Order.objects.get()
    order.expires_at = timezone.now() - timedelta(seconds=1)
    order.payment_backend = 'venty'
    order.save()
    expire_orders()
    item.refresh_from_db()
    assert item.stock == 10
    response, payload = event(client, order)
    assert response.status_code == 200 and response.json()['status'] == 'expired'
    order.refresh_from_db()
    assert order.payment_review_required
    assert event(client, order, **payload)[0].status_code == 200
    item.refresh_from_db()
    assert item.stock == 10


def handoff_exchange(client, token, details=None):
    payload = {'token': token}
    if details is not None:
        payload['details'] = details
    body = json.dumps(payload).encode()
    headers = signed_headers(body)
    return client.post('/api/payments/checkout/', body, content_type='application/json', HTTP_X_MSHOPPA_TIMESTAMP=headers['X-Mshoppa-Timestamp'], HTTP_X_MSHOPPA_SIGNATURE=headers['X-Mshoppa-Signature'])


def test_handoff_opens_payment_page_without_creating_order(client, business, item, simulator):
    from urllib.parse import parse_qs, urlsplit
    items = [{'variant_id':str(item.pk),'quantity':2}]
    response = post(client, business, '/api/checkout/handoff/', {'items':items})
    assert response.status_code == 200
    target = urlsplit(response.json()['payment_url'])
    assert target.hostname == 'localhost' and target.port == 4204
    token = parse_qs(target.query)['checkout'][0]
    assert not Order.objects.exists()
    item.refresh_from_db()
    assert item.stock == 10
    preview = handoff_exchange(client, token)
    assert preview.status_code == 200 and preview.json()['methods'] == ['stripe', 'mpesa']
    assert preview.json()['lines'][0]['quantity'] == 2
    details = {'quote_token':preview.json()['quote_token'],'name':'Checkout Test','email':'checkout@example.test','phone':'0712345678','address':'Test address','provider':'stripe', 'items':[], 'checkout_key':str(uuid.uuid4())}
    created = handoff_exchange(client, token, details)
    assert created.status_code == 201, created.data
    assert preview.json()['order_number'] == created.json()['order_number'] == created.json()['id'][:8].upper()
    assert handoff_exchange(client, token, details).json()['id'] == created.json()['id']
    assert Order.objects.count() == 1
    item.refresh_from_db()
    assert item.stock == 8
    assert handoff_exchange(client, token).json()['order']['id'] == created.json()['id']
    assert '/checkout?order=' in created.json()['return_url']


def test_handoff_rejects_tampering_expiry_and_unsigned_exchange(client, business, item):
    from unittest.mock import patch
    from urllib.parse import parse_qs, urlsplit

    from django.core import signing
    response = post(client,business,'/api/checkout/handoff/',{'items':[{'variant_id':str(item.pk),'quantity':1}]})
    token = parse_qs(urlsplit(response.json()['payment_url']).query)['checkout'][0]
    assert handoff_exchange(client,token+'x').status_code == 400
    assert client.post('/api/payments/checkout/',{'token':token},format='json').status_code == 403
    with patch('apps.checkout.handoff.signing.loads',side_effect=signing.SignatureExpired):
        assert handoff_exchange(client,token).status_code == 400
    business.published = False
    business.save()
    assert handoff_exchange(client,token).status_code == 404
    assert not Order.objects.exists()


def test_customer_tracking_shows_fulfillment_but_never_internal_notes(client, business, item, simulator):
    data, _ = checkout_data(client,business,item)
    result = post(client,business,'/api/checkout/',data).json()
    order = Order.objects.get()
    event(client,order)
    order.refresh_from_db()
    order.fulfillment_status = 'shipped'
    order.tracking_reference = 'DELIVERY-TEST-123'
    order.staff_notes = 'Private warehouse instruction'
    order.save()
    response = client.get(f"/api/orders/{result['token']}/",HTTP_HOST=business.domains.get().hostname)
    assert response.status_code == 200
    assert response.json()['status'] == 'paid'
    assert response.json()['fulfillment_status'] == 'shipped'
    assert response.json()['tracking_reference'] == 'DELIVERY-TEST-123'
    assert 'staff_notes' not in response.json() and 'Private warehouse' not in response.content.decode()
    assert client.get(f"/api/orders/{result['token']}/",HTTP_HOST='another.localhost').status_code == 404


def test_cart_exposes_only_active_variants_with_effective_prices(client, business, item):
    alternate = Variant.objects.create(product=item.product, sku='TOTE-LARGE', label='Large', price='150', offer_price='120', stock=3)
    Variant.objects.create(product=item.product, sku='TOTE-OLD', label='Retired', price='5', stock=10, is_active=False)
    result = post(client,business,'/api/cart/quote/',{'items':[{'variant_id':str(item.pk),'quantity':1}]})
    assert result.status_code == 200
    options = result.json()['lines'][0]['variants']
    assert {option['id'] for option in options} == {str(item.pk),str(alternate.pk)}
    assert next(option for option in options if option['id']==str(alternate.pk)) == {'id':str(alternate.pk),'label':'Large','price':'120.00','stock':3}
