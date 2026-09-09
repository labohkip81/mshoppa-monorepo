import hashlib
import re
import time
from datetime import timedelta

import pyotp
import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import EmailChallenge, OutgoingEmail
from apps.businesses.models import AuditEvent, Business, BusinessApplication, Domain, Membership
from apps.businesses.services import provision_business, review_application
from apps.catalog.models import Product, Variant

pytestmark = pytest.mark.django_db
PASSWORD = "A-test-password-2026!"


@pytest.fixture(autouse=True)
def reset_throttles():
    cache.clear()


@pytest.fixture
def client():
    return APIClient(enforce_csrf_checks=True)


def mutate(client, url, data=None, method="post"):
    token = client.get("/api/auth/csrf/").json()["token"]
    return getattr(client, method)(url, data or {}, format="json", HTTP_X_CSRFTOKEN=token)


@pytest.fixture
def owner():
    return get_user_model().objects.create_user(
        username="owner@example.test",
        email="owner@example.test",
        first_name="Alex",
        password=PASSWORD,
        email_verified=True,
    )


@pytest.fixture
def staff():
    return get_user_model().objects.create_user(
        username="reviewer@example.test",
        email="reviewer@example.test",
        password=PASSWORD,
        email_verified=True,
        is_staff=True,
    )


@pytest.fixture
def application(owner):
    return BusinessApplication.objects.create(
        owner=owner,
        name="Everyday",
        slug="everyday",
        category="Home",
        phone="+254700000000",
        country="KE",
        currency="KES",
        status="pending",
    )


@pytest.fixture
def business(application, staff):
    approved = review_application(application.pk, staff, "approved", "Welcome")
    return provision_business(approved.business_id)


def login(client, user):
    return mutate(client, "/api/auth/login/", {"email": user.email, "password": PASSWORD})


def staff_login(client, staff):
    assert login(client, staff).json()["requires_mfa"]
    setup = mutate(client, "/api/auth/mfa/setup/").json()
    code = pyotp.TOTP(setup["secret"]).now()
    assert mutate(client, "/api/auth/mfa/verify/", {"code": code}).status_code == 200
    return code


def test_sqlite_selected(settings):
    assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3"


def test_storefront_phone_comes_from_its_approved_application(client, owner, business, application):
    BusinessApplication.objects.create(
        owner=owner,
        name="Other applicant",
        slug="other-phone",
        phone="+254711222333",
        country="KE",
        currency="KES",
        status="pending",
    )
    public = client.get("/api/storefront/", HTTP_HOST=business.domains.get().hostname)
    assert public.status_code == 200
    assert public.json()["phone"] == application.phone
    login(client, owner)
    preview = client.get(f"/api/businesses/{business.pk}/preview/")
    assert preview.json()["phone"] == application.phone


def test_storefront_phone_is_empty_without_a_store_contact(client, business, application):
    application.phone = ""
    application.save(update_fields=["phone"])
    response = client.get("/api/storefront/", HTTP_HOST=business.domains.get().hostname)
    assert response.status_code == 200
    assert response.json()["phone"] == ""


def test_preview_link_is_host_bound_and_no_admin_cookie_required(client, owner, business):
    from urllib.parse import urlsplit

    login(client, owner)
    result = mutate(client, f"/api/businesses/{business.pk}/preview-link/")
    assert result.status_code == 200
    url = urlsplit(result.json()["url"])
    assert url.hostname == "everyday.localhost"
    token = url.fragment.removeprefix("preview=")
    shopper = APIClient(enforce_csrf_checks=True)
    result = shopper.get(
        "/api/storefront/preview/",
        HTTP_HOST="everyday.localhost:4203",
        HTTP_X_MSHOPPA_PREVIEW=token,
    )
    assert result.status_code == 200
    assert result.json()["preview"] is True
    assert result["Cache-Control"] == "private, no-store"
    assert (
        shopper.get(
            "/api/storefront/preview/",
            HTTP_HOST="different.localhost",
            HTTP_X_MSHOPPA_PREVIEW=token,
        ).status_code
        == 403
    )
    assert (
        shopper.get("/api/storefront/preview/", HTTP_HOST="everyday.localhost").status_code == 403
    )
    Membership.objects.filter(user=owner, business=business).delete()
    assert (
        shopper.get(
            "/api/storefront/preview/", HTTP_HOST="everyday.localhost", HTTP_X_MSHOPPA_PREVIEW=token
        ).status_code
        == 404
    )


def test_preview_token_expires(client, owner, business, monkeypatch):
    from urllib.parse import urlsplit

    login(client, owner)
    result = mutate(client, f"/api/businesses/{business.pk}/preview-link/")
    token = urlsplit(result.json()["url"]).fragment.removeprefix("preview=")
    now = time.time()
    monkeypatch.setattr("django.core.signing.time.time", lambda: now + 301)
    shopper = APIClient()
    assert (
        shopper.get(
            "/api/storefront/preview/", HTTP_HOST="everyday.localhost", HTTP_X_MSHOPPA_PREVIEW=token
        ).status_code
        == 403
    )


def test_subdomain_csrf_origin_is_not_wildcard(client, owner):
    token = client.get("/api/auth/csrf/", HTTP_HOST="admin.localhost:4201").json()["token"]
    payload = {"email": owner.email, "password": PASSWORD}
    assert (
        client.post(
            "/api/auth/login/",
            payload,
            format="json",
            HTTP_HOST="admin.localhost:4201",
            HTTP_ORIGIN="http://abc.localhost:4203",
            HTTP_X_CSRFTOKEN=token,
        ).status_code
        == 403
    )
    result = client.post(
        "/api/auth/login/",
        payload,
        format="json",
        HTTP_HOST="admin.localhost:4201",
        HTTP_ORIGIN="http://admin.localhost:4201",
        HTTP_X_CSRFTOKEN=token,
    )
    assert result.status_code == 200
    assert not result.cookies["mshoppa_session"]["domain"]


def test_login_requires_csrf(client, owner):
    assert (
        client.post("/api/auth/login/", {"email": owner.email, "password": PASSWORD}).status_code
        == 403
    )
    assert login(client, owner).status_code == 200
    assert client.get("/api/auth/me/").json()["email"] == owner.email
    assert client.post("/api/auth/logout/").status_code == 403
    assert mutate(client, "/api/auth/logout/").status_code == 200
    assert client.get("/api/auth/me/").status_code == 403


def test_signup_verification_one_use(client):
    result = mutate(
        client,
        "/api/auth/register/",
        {"first_name": "Kai", "email": "KAI@example.test", "password": PASSWORD},
    )
    assert result.status_code == 201
    user = get_user_model().objects.get(email="kai@example.test")
    assert not user.email_verified
    assert login(client, user).status_code == 403
    mail = OutgoingEmail.objects.get(recipient=user.email)
    token = re.search(r"token=([A-Za-z0-9_-]+)", mail.body).group(1)
    assert (
        EmailChallenge.objects.get(user=user).digest == hashlib.sha256(token.encode()).hexdigest()
    )
    assert mutate(client, "/api/auth/verify-email/", {"token": token}).status_code == 200
    assert mutate(client, "/api/auth/verify-email/", {"token": token}).status_code == 400
    assert login(client, user).status_code == 200


def test_duplicate_email_and_weak_password(client, owner):
    assert (
        mutate(
            client,
            "/api/auth/register/",
            {"first_name": "Alex", "email": owner.email.upper(), "password": PASSWORD},
        ).status_code
        == 400
    )
    assert (
        mutate(
            client,
            "/api/auth/register/",
            {"first_name": "Alex", "email": "new@example.test", "password": "short"},
        ).status_code
        == 400
    )


def test_expired_verification(client, owner):
    EmailChallenge.objects.create(
        user=owner,
        digest=hashlib.sha256(b"expired").hexdigest(),
        expires_at=timezone.now() - timedelta(seconds=1),
    )
    assert mutate(client, "/api/auth/verify-email/", {"token": "expired"}).status_code == 400


def test_platform_requires_mfa_and_rejects_replay(client, staff, application):
    assert login(client, staff).status_code == 200
    assert client.get("/api/platform/applications/").status_code == 403
    setup = mutate(client, "/api/auth/mfa/setup/").json()
    assert mutate(client, "/api/auth/mfa/verify/", {"code": "000000"}).status_code == 400
    code = pyotp.TOTP(setup["secret"]).now()
    assert mutate(client, "/api/auth/mfa/verify/", {"code": code}).status_code == 200
    assert client.get("/api/platform/applications/").status_code == 200
    staff.refresh_from_db()
    assert staff.mfa_secret != setup["secret"]
    mutate(client, "/api/auth/logout/")
    assert login(client, staff).json()["requires_mfa_setup"] is False
    assert mutate(client, "/api/auth/mfa/verify/", {"code": code}).status_code == 400


def test_mfa_session_expiry(client, staff):
    staff_login(client, staff)
    session = client.session
    session["mfa_at"] = time.time() - 13 * 3600
    session.save()
    assert client.get("/api/platform/applications/").status_code == 403


def test_merchant_cannot_review(client, owner, application):
    login(client, owner)
    assert client.get("/api/platform/applications/").status_code == 403
    result = mutate(
        client, f"/api/platform/applications/{application.pk}/review/", {"decision": "approved"}
    )
    assert result.status_code == 403
    assert not Business.objects.exists()


def test_approval_and_provisioning_idempotent(client, staff, application):
    staff_login(client, staff)
    url = f"/api/platform/applications/{application.pk}/review/"
    first = mutate(client, url, {"decision": "approved"})
    second = mutate(client, url, {"decision": "approved"})
    assert first.status_code == second.status_code == 200
    assert first.json()["business"] == second.json()["business"]
    assert Business.objects.count() == Membership.objects.count() == 1
    assert OutgoingEmail.objects.count() == 1
    provision_business(first.json()["business"])
    provision_business(first.json()["business"])
    assert Domain.objects.count() == 1
    assert AuditEvent.objects.filter(action="business.provisioned").count() == 1
    assert Business.objects.get().published


def test_changes_resubmit_and_reserved_address(client, owner, staff, application):
    staff_login(client, staff)
    url = f"/api/platform/applications/{application.pk}/review/"
    assert mutate(client, url, {"decision": "changes_requested"}).status_code == 400
    assert (
        mutate(
            client, url, {"decision": "changes_requested", "note": "Please clarify your products."}
        ).status_code
        == 200
    )
    mutate(client, "/api/auth/logout/")
    login(client, owner)
    assert (
        mutate(
            client,
            f"/api/applications/{application.pk}/",
            {"description": "Handmade homeware"},
            "patch",
        ).status_code
        == 200
    )
    assert mutate(client, f"/api/applications/{application.pk}/submit/").status_code == 200
    assert (
        mutate(
            client,
            f"/api/applications/{application.pk}/",
            {"name": "Change after submission"},
            "patch",
        ).status_code
        == 400
    )
    payload = {
        "name": "Test",
        "slug": "admin",
        "category": "Home",
        "phone": "+254700000000",
        "country": "KE",
        "currency": "KES",
    }
    assert mutate(client, "/api/applications/", payload).status_code == 400


def test_cross_tenant_access_fails_closed(client, owner, business):
    other = get_user_model().objects.create_user(
        username="other@example.test",
        email="other@example.test",
        password=PASSWORD,
        email_verified=True,
    )
    alien = Business.objects.create(
        name="Other", slug="other", country="KE", currency="KES", provisioning_status="ready"
    )
    Membership.objects.create(user=other, business=alien, role="owner")
    product = Product.objects.create(business=alien, name="Private", slug="private")
    alien_application = BusinessApplication.objects.create(
        owner=other,
        business=alien,
        name="Other",
        slug="other",
        country="KE",
        currency="KES",
        status="approved",
    )
    login(client, owner)
    stores = client.get("/api/businesses/").json()["results"]
    assert [store["id"] for store in stores] == [str(business.pk)]
    for url in [
        f"/api/businesses/{alien.pk}/",
        f"/api/businesses/{alien.pk}/settings/",
        f"/api/businesses/{alien.pk}/products/",
        f"/api/businesses/{alien.pk}/preview/",
        f"/api/businesses/{business.pk}/products/{product.pk}/",
        f"/api/applications/{alien_application.pk}/",
    ]:
        assert client.get(url).status_code == 404, url
    assert (
        mutate(
            client,
            f"/api/businesses/{alien.pk}/products/",
            {"name": "Attack", "price": "1.00", "stock": 1},
        ).status_code
        == 404
    )
    assert (
        mutate(
            client, f"/api/businesses/{alien.pk}/settings/", {"headline": "Attack"}, "patch"
        ).status_code
        == 404
    )
    result = mutate(
        client,
        f"/api/businesses/{business.pk}/products/",
        {"name": "Owned", "price": "2.00", "stock": 2, "business": str(alien.pk)},
    )
    assert result.status_code == 201
    assert Product.objects.get(pk=result.json()["id"]).business_id == business.pk


def test_settings_and_draft_product_persist(client, owner, business):
    login(client, owner)
    result = mutate(
        client,
        f"/api/businesses/{business.pk}/settings/",
        {"headline": "A better everyday.", "surface_tone": "sky"},
        "patch",
    )
    assert result.status_code == 200
    assert (
        client.get(f"/api/businesses/{business.pk}/settings/").json()["headline"]
        == "A better everyday."
    )
    result = mutate(
        client,
        f"/api/businesses/{business.pk}/products/",
        {"name": "Canvas tote", "price": "1250.00", "stock": 4},
    )
    assert result.status_code == 201
    assert result.json()["status"] == "draft"
    assert Variant.objects.get().price == 1250
    assert (
        client.get(f"/api/businesses/{business.pk}/preview/").json()["products"][0]["name"]
        == "Canvas tote"
    )
    assert (
        mutate(
            client,
            f"/api/businesses/{business.pk}/products/",
            {"name": "Invalid", "price": "-1", "stock": 0},
        ).status_code
        == 400
    )
    assert (
        mutate(
            client,
            f"/api/businesses/{business.pk}/products/",
            {"name": "Invalid", "price": "1", "stock": -1},
        ).status_code
        == 400
    )


def test_support_role_and_suspension_prevent_writes(client, owner, business):
    login(client, owner)
    Membership.objects.filter(user=owner).update(role="support")
    assert client.get(f"/api/businesses/{business.pk}/products/").status_code == 200
    assert (
        mutate(
            client,
            f"/api/businesses/{business.pk}/products/",
            {"name": "No", "price": "1", "stock": 1},
        ).status_code
        == 403
    )
    Membership.objects.filter(user=owner).update(role="owner")
    business.suspended = True
    business.save()
    assert (
        mutate(
            client, f"/api/businesses/{business.pk}/settings/", {"headline": "No"}, "patch"
        ).status_code
        == 403
    )


def test_public_store_requires_exact_verified_published_host(client, business):
    host = business.domains.get().hostname
    business.published = False
    business.save()
    assert client.get("/api/storefront/", HTTP_HOST=host).status_code == 404
    business.published = True
    business.save()
    Product.objects.create(business=business, name="Hidden draft", slug="hidden")
    assert client.get("/api/storefront/", HTTP_HOST=host).json()["products"] == []
    assert client.get("/api/storefront/", HTTP_HOST="unknown.mshoppa.localhost").status_code == 404
    Domain.objects.filter(business=business).update(verified=False)
    assert client.get("/api/storefront/", HTTP_HOST=host).status_code == 404


def test_owner_can_take_store_offline_and_retries_preserve_choice(client, owner, business):
    login(client, owner)
    host = business.domains.get().hostname
    assert client.get("/api/storefront/", HTTP_HOST=host).status_code == 200
    url = f"/api/businesses/{business.pk}/settings/"
    assert mutate(client, url, {"published": False}, "patch").status_code == 200
    assert client.get(url).json()["published"] is False
    assert client.get("/api/storefront/", HTTP_HOST=host).status_code == 404
    provision_business(business.pk)
    assert client.get("/api/storefront/", HTTP_HOST=host).status_code == 404
    assert mutate(client, url, {"published": True}, "patch").status_code == 200
    assert client.get("/api/storefront/", HTTP_HOST=host).status_code == 200


def test_local_worker_delivers_outbox_once(client, owner, settings, tmp_path):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    mutate(
        client,
        "/api/auth/register/",
        {"first_name": "Test", "email": "mail@example.test", "password": PASSWORD},
    )
    call_command("process_jobs", once=True)
    call_command("process_jobs", once=True)
    from django.core import mail

    assert len(mail.outbox) == 1
    assert OutgoingEmail.objects.get().sent_at is not None


@pytest.fixture
def image_file(settings, tmp_path):
    from io import BytesIO

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image, PngImagePlugin

    settings.MEDIA_ROOT = tmp_path / "media"

    def make(name="bag.png"):
        output = BytesIO()
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("private_note", "must not survive normalization")
        Image.new("RGB", (80, 60), "#d1b0a4").save(output, format="PNG", pnginfo=metadata)
        return SimpleUploadedFile(name, output.getvalue(), content_type="image/png")

    return make


@pytest.fixture
def product(client, owner, business):
    login(client, owner)
    result = mutate(
        client,
        f"/api/businesses/{business.pk}/products/",
        {"name": "Fossil Bag", "category": "Bag", "price": "10000.00", "stock": 100},
    )
    return Product.objects.get(pk=result.json()["id"])


def upload_image(client, business, product, file):
    token = client.get("/api/auth/csrf/").json()["token"]
    return client.post(
        f"/api/businesses/{business.pk}/products/{product.pk}/images/",
        {"image": file},
        format="multipart",
        HTTP_X_CSRFTOKEN=token,
    )


def test_edit_product_offer_and_clear(client, business, product):
    variant = product.variants.get()
    sku, slug = variant.sku, product.slug
    url = f"/api/businesses/{business.pk}/products/{product.pk}/"
    result = mutate(
        client,
        url,
        {
            "name": "Fossil Weekender",
            "description": "Leather carryall",
            "category": "Travel",
            "price": "9500.00",
            "offer_price": "8000.00",
            "stock": 88,
            "status": "published",
        },
        "patch",
    )
    assert result.status_code == 200
    assert result.json()["variants"][0]["offer_price"] == "8000.00"
    variant.refresh_from_db()
    product.refresh_from_db()
    assert variant.sku == sku and product.slug == slug
    assert variant.stock == 88 and product.name == "Fossil Weekender"
    public = client.get("/api/storefront/", HTTP_HOST=business.domains.get().hostname).json()
    assert public["products"][0]["variants"][0]["offer_price"] == "8000.00"
    # Updating regular price must also validate any retained offer.
    assert mutate(client, url, {"price": "7500.00"}, "patch").status_code == 400
    assert mutate(client, url, {"offer_price": None}, "patch").status_code == 200
    assert client.get(url).json()["variants"][0]["offer_price"] is None
    assert AuditEvent.objects.filter(action="product.updated", business=business).count() == 2


@pytest.mark.parametrize("offer", ["10000.00", "12000.00", "-1.00", "8.999", "not-a-price"])
def test_offer_validation_is_atomic(client, business, product, offer):
    url = f"/api/businesses/{business.pk}/products/{product.pk}/"
    result = mutate(client, url, {"name": "Must not save", "offer_price": offer}, "patch")
    assert result.status_code == 400
    product.refresh_from_db()
    assert product.name == "Fossil Bag"


def test_zero_offer_and_whole_currency_rules(client, business, product):
    url = f"/api/businesses/{business.pk}/products/{product.pk}/"
    assert mutate(client, url, {"offer_price": "0.00"}, "patch").status_code == 200
    business.currency = "UGX"
    business.save()
    assert mutate(client, url, {"offer_price": "10.50"}, "patch").status_code == 400
    assert mutate(client, url, {"offer_price": "10.00"}, "patch").status_code == 200


def test_upload_preview_remove_and_invalid_media_capabilities(
    client, business, product, image_file
):
    from io import BytesIO

    from PIL import Image

    from apps.catalog.models import ProductImage

    result = upload_image(client, business, product, image_file())
    assert result.status_code == 201
    image = ProductImage.objects.get(pk=result.json()["id"])
    assert str(business.pk) in image.file.name
    assert image.width == 80 and image.height == 60
    response = APIClient().get(result.json()["url"])
    assert response.status_code == 200 and response["Content-Type"] == "image/webp"
    with Image.open(BytesIO(b"".join(response.streaming_content))) as decoded:
        assert decoded.format == "WEBP" and "private_note" not in decoded.info
    assert APIClient().get(f"/api/product-images/{image.pk}/content/").status_code == 403
    second = upload_image(client, business, product, image_file("second.png")).json()
    assert (
        APIClient().get(result.json()["url"].replace(str(image.pk), second["id"], 1)).status_code
        == 403
    )
    path = image.file.path
    remove = f"/api/businesses/{business.pk}/products/{product.pk}/images/{image.pk}/"
    assert mutate(client, remove, method="delete").status_code == 204
    assert APIClient().get(result.json()["url"]).status_code == 404
    from pathlib import Path

    assert Path(path).exists()  # Local file retained for recovery, never served after removal.
    assert (
        client.get(f"/api/businesses/{business.pk}/products/{product.pk}/").json()["images"][0][
            "id"
        ]
        == second["id"]
    )


def test_image_expiry(client, business, product, image_file, monkeypatch):
    result = upload_image(client, business, product, image_file())
    now = time.time()
    monkeypatch.setattr("django.core.signing.time.time", lambda: now + 3601)
    assert APIClient().get(result.json()["url"]).status_code == 403


def test_reject_invalid_oversized_and_excess_images(client, business, product, image_file):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.catalog.models import ProductImage

    assert (
        upload_image(
            client,
            business,
            product,
            SimpleUploadedFile(
                "fake.jpg", b"<svg><script>bad</script></svg>", content_type="image/jpeg"
            ),
        ).status_code
        == 400
    )
    assert (
        upload_image(
            client,
            business,
            product,
            SimpleUploadedFile("huge.png", b"0" * (5 * 1024 * 1024 + 1), content_type="image/png"),
        ).status_code
        == 400
    )
    assert not ProductImage.objects.exists()
    for _ in range(8):
        assert upload_image(client, business, product, image_file()).status_code == 201
    assert upload_image(client, business, product, image_file()).status_code == 400
    assert ProductImage.objects.count() == 8


def test_image_and_edit_require_business_scope_and_write_role(
    client, owner, business, product, image_file
):
    from apps.catalog.models import ProductImage

    result = upload_image(client, business, product, image_file()).json()
    other = get_user_model().objects.create_user(
        username="catalog-other@example.test",
        email="catalog-other@example.test",
        password=PASSWORD,
        email_verified=True,
    )
    alien = Business.objects.create(
        name="Alien", slug="alien", currency="KES", country="KE", provisioning_status="ready"
    )
    Membership.objects.create(user=other, business=alien, role="owner")
    other_product = Product.objects.create(business=alien, name="Other", slug="other")
    # An image ID cannot be moved or deleted by supplying another product in the same store.
    own_other_product = Product.objects.create(
        business=business, name="Own other", slug="own-other"
    )
    assert (
        mutate(
            client,
            f"/api/businesses/{business.pk}/products/{own_other_product.pk}/images/{result['id']}/",
            method="delete",
        ).status_code
        == 404
    )
    assert (
        mutate(
            client,
            f"/api/businesses/{alien.pk}/products/{other_product.pk}/",
            {"name": "Attack"},
            "patch",
        ).status_code
        == 404
    )
    assert upload_image(client, alien, other_product, image_file()).status_code == 404
    mutate(client, "/api/auth/logout/")
    login(client, other)
    assert (
        mutate(
            client, f"/api/businesses/{business.pk}/products/{product.pk}/", {"price": "1"}, "patch"
        ).status_code
        == 404
    )
    assert upload_image(client, business, product, image_file()).status_code == 404
    assert (
        mutate(
            client,
            f"/api/businesses/{business.pk}/products/{product.pk}/images/{result['id']}/",
            method="delete",
        ).status_code
        == 404
    )
    mutate(client, "/api/auth/logout/")
    login(client, owner)
    Membership.objects.filter(user=owner, business=business).update(role="support")
    assert upload_image(client, business, product, image_file()).status_code == 403
    assert (
        mutate(
            client, f"/api/businesses/{business.pk}/products/{product.pk}/", {"name": "No"}, "patch"
        ).status_code
        == 403
    )
    assert ProductImage.objects.count() == 1


def test_upload_and_edit_require_csrf(client, business, product, image_file):
    url = f"/api/businesses/{business.pk}/products/{product.pk}/"
    assert client.patch(url, {"price": "1"}, format="json").status_code == 403
    assert (
        client.post(url + "images/", {"image": image_file()}, format="multipart").status_code == 403
    )
