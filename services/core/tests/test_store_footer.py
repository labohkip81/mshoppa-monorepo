# Imported pytest fixtures are injected into tests by name.
# ruff: noqa: F811
import pytest
from rest_framework.test import APIClient

from apps.businesses.models import Business, Membership
from tests.test_foundation import (  # noqa: F401
    application,
    business,
    client,
    image_file,
    login,
    mutate,
    owner,
    reset_throttles,
    staff,
)

pytestmark = pytest.mark.django_db


def test_footer_fields_persist_and_remain_scoped(client, owner, business):
    login(client, owner)
    url = f"/api/businesses/{business.pk}/settings/"
    fields = {
        "description": "Thoughtfully made homeware.",
        "contact_email": "store@example.test",
        "contact_phone": "+254 711 222 333",
        "contact_address": "Studio 5\nNairobi",
        "whatsapp_number": "+254 722 333 444",
        "instagram_url": "https://www.instagram.com/example/",
        "return_refund_policy": "Returns by arrangement.\nContact the store.",
        "privacy_policy": "Our privacy policy.",
        "terms_conditions": "Our store terms.",
    }
    result = mutate(client, url, fields, "patch")
    assert result.status_code == 200
    assert result.json()["whatsapp_number"] == "+254722333444"
    public = APIClient().get("/api/storefront/", HTTP_HOST=business.domains.get().hostname).json()
    assert public["phone"] == "+254711222333"
    assert public["settings"]["return_refund_policy"] == fields["return_refund_policy"]
    assert public["settings"]["description"] == fields["description"]
    alien = Business.objects.create(name="Other", slug="other-footer", country="KE", currency="KES")
    assert (
        mutate(client, f"/api/businesses/{alien.pk}/settings/", fields, "patch").status_code == 404
    )
    Membership.objects.filter(business=business, user=owner).update(role="support")
    assert mutate(client, url, fields, "patch").status_code == 403


def test_blank_footer_values_have_no_invented_content(client, owner, business):
    login(client, owner)
    fields = {
        key: ""
        for key in [
            "description",
            "contact_email",
            "contact_address",
            "whatsapp_number",
            "instagram_url",
            "facebook_url",
            "tiktok_url",
            "x_url",
            "linkedin_url",
            "return_refund_policy",
            "privacy_policy",
            "terms_conditions",
        ]
    }
    result = mutate(client, f"/api/businesses/{business.pk}/settings/", fields, "patch")
    assert result.status_code == 200
    public = (
        APIClient()
        .get("/api/storefront/", HTTP_HOST=business.domains.get().hostname)
        .json()["settings"]
    )
    assert all(public[field] == "" for field in fields)
    assert public["logo_url"] == ""


@pytest.mark.parametrize(
    "field,value",
    [
        ("instagram_url", "javascript:alert(1)"),
        ("facebook_url", "ftp://example.com/file"),
        ("linkedin_url", "https://user:password@example.com"),
        ("whatsapp_number", "not-a-number"),
        ("whatsapp_number", "0711222333"),
    ],
)
def test_footer_rejects_unsafe_links_and_invalid_whatsapp(client, owner, business, field, value):
    login(client, owner)
    assert (
        mutate(
            client, f"/api/businesses/{business.pk}/settings/", {field: value}, "patch"
        ).status_code
        == 400
    )


def test_logo_upload_replace_remove_and_scope(client, owner, business, image_file):
    login(client, owner)
    url = f"/api/businesses/{business.pk}/logo/"
    csrf = client.get("/api/auth/csrf/").json()["token"]
    assert client.post(url, {"image": image_file()}, format="multipart").status_code == 403
    first = client.post(url, {"image": image_file()}, format="multipart", HTTP_X_CSRFTOKEN=csrf)
    assert first.status_code == 200
    first_url = first.json()["logo_url"]
    response = APIClient().get(first_url)
    assert response.status_code == 200 and response["Content-Type"] == "image/webp"
    response.close()
    assert APIClient().get(f"/api/store-logos/{business.pk}/").status_code == 403
    alien = Business.objects.create(name="Other", slug="alien-logo", country="KE", currency="KES")
    assert (
        client.post(
            f"/api/businesses/{alien.pk}/logo/",
            {"image": image_file()},
            format="multipart",
            HTTP_X_CSRFTOKEN=csrf,
        ).status_code
        == 404
    )
    assert APIClient().get(first_url.replace(str(business.pk), str(alien.pk), 1)).status_code == 404
    second = client.post(url, {"image": image_file()}, format="multipart", HTTP_X_CSRFTOKEN=csrf)
    assert second.status_code == 200 and second.json()["logo_url"] != first_url
    assert APIClient().get(first_url).status_code == 404
    assert mutate(client, url, method="delete").status_code == 200
    assert APIClient().get(second.json()["logo_url"]).status_code == 404
    assert client.get(f"/api/businesses/{business.pk}/settings/").json()["logo_url"] == ""


def test_logo_validation_permissions_and_expiry(client, owner, business, image_file, monkeypatch):
    import time

    from django.core.files.uploadedfile import SimpleUploadedFile

    login(client, owner)
    url = f"/api/businesses/{business.pk}/logo/"
    csrf = client.get("/api/auth/csrf/").json()["token"]
    fake = SimpleUploadedFile("fake.png", b"<script>alert(1)</script>", content_type="image/png")
    assert (
        client.post(url, {"image": fake}, format="multipart", HTTP_X_CSRFTOKEN=csrf).status_code
        == 400
    )
    saved = client.post(
        url, {"image": image_file()}, format="multipart", HTTP_X_CSRFTOKEN=csrf
    ).json()
    Membership.objects.filter(business=business, user=owner).update(role="support")
    assert (
        client.post(
            url, {"image": image_file()}, format="multipart", HTTP_X_CSRFTOKEN=csrf
        ).status_code
        == 403
    )
    assert mutate(client, url, method="delete").status_code == 403
    now = time.time()
    monkeypatch.setattr("django.core.signing.time.time", lambda: now + 3601)
    assert APIClient().get(saved["logo_url"]).status_code == 403
