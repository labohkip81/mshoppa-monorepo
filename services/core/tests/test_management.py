# ruff: noqa: F811
import uuid
from datetime import timedelta
from io import BytesIO

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image

from apps.businesses.models import Business, Domain, Membership
from apps.catalog.models import Product, Variant
from apps.checkout.models import Order
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
def local(settings, tmp_path):
    settings.DEBUG = True
    settings.BASE_DOMAIN = "localhost"
    settings.MEDIA_ROOT = tmp_path


def make_order(business, **kwargs):
    data = dict(
        business=business,
        checkout_key=uuid.uuid4(),
        request_hash="test",
        email="buyer@example.test",
        customer_name="Buyer",
        address="Nairobi",
        currency="KES",
        subtotal="100",
        tax="0",
        total="100",
        tax_rate="0",
        provider="mpesa",
        status="paid",
        expires_at=timezone.now() + timedelta(minutes=15),
    )
    data.update(kwargs)
    return Order.objects.create(**data)


def url(business, resource, pk=None):
    return f"/api/businesses/{business.pk}/{resource}/" + (f"{pk}/" if pk else "")


def colleague(email="helper@example.test"):
    return get_user_model().objects.create_user(
        username=email, email=email, password="A-test-password-2026!", email_verified=True
    )


def test_orders_fulfillment_and_payment_state_are_separate(client, owner, business):
    order = make_order(business)
    login(client, owner)
    listing = client.get(url(business, "orders")).json()
    assert listing["count"] == 1
    assert "token" not in listing["results"][0]
    assert "request_hash" not in listing["results"][0]
    response = mutate(
        client,
        url(business, "orders", order.pk),
        {
            "fulfillment_status": "shipped",
            "tracking_reference": "LOCAL-123",
            "staff_notes": "Ready for pickup",
            "status": "failed",
        },
        method="patch",
    )
    assert response.status_code == 200, response.data
    order.refresh_from_db()
    assert order.status == "paid" and order.fulfillment_status == "shipped"
    assert order.tracking_reference == "LOCAL-123"
    assert (
        mutate(
            client,
            url(business, "orders", order.pk),
            {"fulfillment_status": "processing"},
            method="patch",
        ).status_code
        == 400
    )
    pending = make_order(business, status="pending")
    assert (
        mutate(
            client,
            url(business, "orders", pending.pk),
            {"fulfillment_status": "shipped"},
            method="patch",
        ).status_code
        == 400
    )
    assert (
        mutate(
            client,
            url(business, "orders", pending.pk),
            {"staff_notes": "Awaiting payment"},
            method="patch",
        ).status_code
        == 200
    )
    assert (
        client.patch(
            url(business, "orders", order.pk), {"staff_notes": "No CSRF"}, format="json"
        ).status_code
        == 403
    )


def test_store_isolation_across_management_endpoints(client, owner, business):
    other = Business.objects.create(
        name="Other", slug="other-shop", currency="KES", country="KE", provisioning_status="ready"
    )
    order = make_order(other)
    domain = Domain.objects.create(business=other, hostname="other-shop.localhost")
    helper = colleague()
    member = Membership.objects.create(business=other, user=helper, role="owner")
    product = Product.objects.create(business=other, name="Private", slug="private")
    variant = Variant.objects.create(product=product, sku="PRIVATE", price=100, stock=2)
    login(client, owner)
    for resource in ["orders", "payments", "customers", "staff", "domains", "promotions"]:
        assert client.get(url(other, resource)).status_code == 404
        assert client.get(url(business, resource)).status_code == 200
    for resource, pk, data in [
        ("orders", order.pk, {"staff_notes": "cross-tenant"}),
        ("domains", domain.pk, {"is_primary": True}),
        ("staff", member.pk, {"role": "support"}),
        ("promotions", variant.pk, {"offer_price": "1"}),
    ]:
        assert mutate(client, url(business, resource, pk), data, method="patch").status_code == 404
    assert (
        mutate(
            client, f"/api/businesses/{other.pk}/", {"name": "Changed"}, method="patch"
        ).status_code
        == 404
    )


def test_customer_aggregation_and_payment_filters(client, owner, business):
    make_order(business, email="BUYER@example.test")
    make_order(business, email="buyer@example.test", status="failed", total=20)
    make_order(business, email="second@example.test", provider="stripe", total=40)
    login(client, owner)
    customers = client.get(url(business, "customers") + "?q=buyer").json()["results"]
    assert len(customers) == 1 and customers[0]["order_count"] == 2
    assert customers[0]["paid_total"] == "100.00"
    assert client.get(url(business, "orders") + "?email=buyer@example.test").json()["count"] == 2
    payments = client.get(url(business, "payments") + "?provider=mpesa&status=paid").json()
    assert payments["count"] == 1
    assert "token" not in payments["results"][0]


def test_staff_roles_owner_protection_and_revocation(client, owner, business):
    helper = colleague()
    login(client, owner)
    response = mutate(client, url(business, "staff"), {"email": helper.email, "role": "support"})
    assert response.status_code == 201, response.data
    member_id = response.json()["id"]
    assert (
        mutate(
            client, url(business, "staff"), {"email": helper.email, "role": "manager"}
        ).status_code
        == 400
    )
    own_member = Membership.objects.get(user=owner, business=business)
    assert mutate(client, url(business, "staff", own_member.pk), method="delete").status_code == 400
    order = make_order(business)
    login(client, helper)
    assert client.get(url(business, "orders")).status_code == 200
    assert client.get(url(business, "payments")).status_code == 403
    assert client.get(url(business, "staff")).status_code == 403
    assert (
        mutate(
            client, url(business, "orders", order.pk), {"staff_notes": "Forbidden"}, method="patch"
        ).status_code
        == 403
    )
    login(client, owner)
    assert (
        mutate(
            client, url(business, "staff", member_id), {"role": "fulfillment"}, method="patch"
        ).status_code
        == 200
    )
    login(client, helper)
    assert (
        mutate(
            client,
            url(business, "orders", order.pk),
            {"fulfillment_status": "processing"},
            method="patch",
        ).status_code
        == 200
    )
    login(client, owner)
    assert mutate(client, url(business, "staff", member_id), method="delete").status_code == 204
    login(client, helper)
    assert client.get(url(business, "orders")).status_code == 404


def test_domains_primary_reserved_conflicts_and_removal(client, owner, business):
    login(client, owner)
    original = business.domains.get()
    response = mutate(client, url(business, "domains"), {"hostname": "new-alias.localhost"})
    assert response.status_code == 201, response.data
    alias_id = response.json()["id"]
    assert response.json()["verified"] is True
    for hostname in [
        "admin.localhost",
        "example.com",
        "https://example.localhost",
        "new-alias.localhost",
        "nested.shop.localhost",
    ]:
        assert mutate(client, url(business, "domains"), {"hostname": hostname}).status_code == 400
    assert mutate(client, url(business, "domains", original.pk), method="delete").status_code == 400
    assert (
        mutate(
            client, url(business, "domains", alias_id), {"is_primary": True}, method="patch"
        ).status_code
        == 200
    )
    assert business.domains.filter(is_primary=True).count() == 1
    assert client.get("/api/storefront/", HTTP_HOST="new-alias.localhost").status_code == 200
    assert mutate(client, url(business, "domains", original.pk), method="delete").status_code == 204
    assert client.get("/api/storefront/", HTTP_HOST=original.hostname).status_code == 404


def test_promotions_change_only_offer_and_affect_public_price(client, owner, business):
    product = Product.objects.create(
        business=business, name="Tote", slug="tote", status="published", category="Bags"
    )
    variant = Variant.objects.create(product=product, sku="TOTE", price=100, stock=5)
    login(client, owner)
    endpoint = url(business, "promotions", variant.pk)
    assert (
        mutate(
            client, endpoint, {"offer_price": "80", "stock": 0, "price": 1}, method="patch"
        ).status_code
        == 200
    )
    variant.refresh_from_db()
    assert variant.offer_price == 80 and variant.stock == 5 and variant.price == 100
    public = client.get("/api/storefront/", HTTP_HOST=business.domains.get().hostname).json()
    assert public["products"][0]["variants"][0]["offer_price"] == "80.00"
    assert client.get(url(business, "promotions") + "?active=true").json()["count"] == 1
    assert mutate(client, endpoint, {"offer_price": "100"}, method="patch").status_code == 400
    assert mutate(client, endpoint, {"offer_price": None}, method="patch").status_code == 200
    assert client.get(url(business, "promotions") + "?active=true").json()["count"] == 0


def image_upload(name="cover.png"):
    data = BytesIO()
    Image.new("RGB", (900, 250), "teal").save(data, format="PNG")
    return SimpleUploadedFile(name, data.getvalue(), content_type="image/png")


def test_cover_upload_isolation_validation_and_replacement(client, owner, business):
    login(client, owner)
    endpoint = url(business, "cover")
    token = client.get("/api/auth/csrf/").json()["token"]
    response = client.post(
        endpoint, {"image": image_upload()}, format="multipart", HTTP_X_CSRFTOKEN=token
    )
    assert response.status_code == 200, response.data
    cover_url = response.json()["cover_url"]
    assert client.get(cover_url).status_code == 200
    public = client.get("/api/storefront/", HTTP_HOST=business.domains.get().hostname).json()
    assert public["settings"]["cover_url"]
    response = client.post(
        endpoint, {"image": image_upload()}, format="multipart", HTTP_X_CSRFTOKEN=token
    )
    assert response.status_code == 200
    assert client.get(cover_url).status_code == 404
    assert (
        client.post(
            endpoint,
            {"image": SimpleUploadedFile("bad.png", b"not an image")},
            format="multipart",
            HTTP_X_CSRFTOKEN=token,
        ).status_code
        == 400
    )
    replacement = response.json()["cover_url"]
    outsider = colleague()
    login(client, outsider)
    assert mutate(client, endpoint, method="delete").status_code == 404
    login(client, owner)
    assert mutate(client, endpoint, method="delete").status_code == 200
    assert client.get(replacement).status_code == 404
    assert not client.get("/api/storefront/", HTTP_HOST=business.domains.get().hostname).json()[
        "settings"
    ]["cover_url"]


def test_storefront_categories_sort_and_featured(client, owner, business):
    products = []
    for name, category, price, status in [
        ("Zebra", "Bags", 100, "published"),
        ("Alpha", "Home", 200, "published"),
        ("Draft", "Secret", 1, "draft"),
    ]:
        product = Product.objects.create(
            business=business, name=name, slug=name.lower(), category=category, status=status
        )
        Variant.objects.create(
            product=product,
            sku=name,
            price=price,
            offer_price=50 if name == "Alpha" else None,
            stock=5,
        )
        products.append(product)
    settings = business.store_settings
    settings.featured_product = products[0]
    settings.save()
    host = business.domains.get().hostname
    result = client.get("/api/storefront/?sort=price-low", HTTP_HOST=host).json()
    assert result["categories"] == ["Bags", "Home"]
    assert [p["name"] for p in result["products"]] == ["Alpha", "Zebra"]
    result = client.get("/api/storefront/?category=Bags&sort=name", HTTP_HOST=host).json()
    assert result["products_count"] == 1 and result["products"][0]["name"] == "Zebra"
    assert client.get("/api/storefront/", HTTP_HOST=host).json()["products"][0]["name"] == "Zebra"
