# Imported pytest fixtures are injected by name into the tests below.
# ruff: noqa: F811
import pytest
from rest_framework.test import APIClient

from apps.businesses.models import Business
from apps.businesses.storefront import storefront_data
from apps.catalog.models import Product
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


def live(business, name):
    return Product.objects.create(
        business=business, name=name, slug=name.lower().replace(" ", "-"), status="published"
    )


def test_public_product_link_only_resolves_live_products_in_this_store(business):
    product = live(business, "Public product")
    draft = Product.objects.create(business=business, name="Draft", slug="draft")
    alien = Business.objects.create(
        name="Other", slug="other-product-shop", country="KE", currency="KES"
    )
    alien_product = live(alien, "Other product")
    api = APIClient()
    host = business.domains.get().hostname
    response = api.get("/api/storefront/", {"product": product.slug}, HTTP_HOST=host)
    assert response.status_code == 200
    assert response.json()["product"]["id"] == str(product.pk)
    for slug in [draft.slug, alien_product.slug, "missing-product"]:
        assert api.get("/api/storefront/", {"product": slug}, HTTP_HOST=host).status_code == 404
    product.status = "draft"
    product.save()
    assert api.get("/api/storefront/", {"product": product.slug}, HTTP_HOST=host).status_code == 404


def test_public_product_link_respects_store_visibility(business):
    product = live(business, "Public product")
    api = APIClient()
    host = business.domains.get().hostname
    for field in ["published", "suspended"]:
        business.published = field != "published"
        business.suspended = field == "suspended"
        business.save()
        assert (
            api.get("/api/storefront/", {"product": product.slug}, HTTP_HOST=host).status_code
            == 404
        )
    assert (
        api.get(
            "/api/storefront/", {"product": product.slug}, HTTP_HOST="unknown.localhost"
        ).status_code
        == 404
    )


def test_admin_shop_url_uses_verified_primary_domain(client, owner, business, settings):
    login(client, owner)
    settings.STOREFRONT_URL_PATTERN = "http://{hostname}:4203"
    result = client.get("/api/businesses/").json()["results"][0]
    domain = business.domains.get()
    assert result["storefront_url"] == f"http://{domain.hostname}:4203"
    domain.verified = False
    domain.save()
    assert client.get("/api/businesses/").json()["results"][0]["storefront_url"] == ""


def test_featured_uses_latest_live_then_selection_then_fallback(business):
    older = live(business, "Older")
    newest = live(business, "Newest")
    Product.objects.create(business=business, name="Draft", slug="draft")
    assert storefront_data(business)["featured_product"]["id"] == str(newest.pk)
    settings = business.store_settings
    settings.featured_product = older
    settings.save()
    assert storefront_data(business)["featured_product"]["id"] == str(older.pk)
    older.status = "draft"
    older.save()
    assert storefront_data(business)["featured_product"]["id"] == str(newest.pk)
    assert "featured_product" not in storefront_data(business)["settings"]
    newest.delete()
    assert storefront_data(business)["featured_product"] is None
    assert storefront_data(business, preview=True)["featured_product"] is None


def test_featured_selection_and_clear_are_persisted_and_scoped(client, owner, business):
    login(client, owner)
    chosen = live(business, "Chosen")
    newest = live(business, "Newest")
    draft = Product.objects.create(business=business, name="Draft", slug="draft")
    alien = Business.objects.create(name="Other", slug="other", country="KE", currency="KES")
    alien_product = live(alien, "Other product")
    url = f"/api/businesses/{business.pk}/settings/"
    for invalid in [draft, alien_product]:
        assert (
            mutate(client, url, {"featured_product": str(invalid.pk)}, "patch").status_code == 400
        )
    result = mutate(client, url, {"featured_product": str(chosen.pk)}, "patch")
    assert result.status_code == 200
    assert result.json()["featured_product"] == str(chosen.pk)
    business.refresh_from_db()
    assert storefront_data(business)["featured_product"]["id"] == str(chosen.pk)
    assert mutate(client, url, {"featured_product": None}, "patch").status_code == 200
    business.refresh_from_db()
    assert storefront_data(business)["featured_product"]["id"] == str(newest.pk)


def test_deleted_featured_choice_clears_and_falls_back(business):
    chosen = live(business, "Chosen")
    fallback = live(business, "Fallback")
    settings = business.store_settings
    settings.featured_product = chosen
    settings.save()
    chosen.delete()
    business.refresh_from_db()
    assert business.store_settings.featured_product_id is None
    assert storefront_data(business)["featured_product"]["id"] == str(fallback.pk)


def test_featured_and_search_can_find_products_beyond_first_page(business):
    oldest = live(business, "Fossil Bag")
    for i in range(25):
        live(business, f"Shoe {i}")
    settings = business.store_settings
    settings.featured_product = oldest
    settings.save()
    data = storefront_data(business)
    assert len(data["products"]) == 24 and data["has_more"]
    assert data["products_count"] == 26
    assert data["featured_product"]["id"] == str(oldest.pk)
    result = storefront_data(business, query="  fOsSiL  ")
    assert result["products_count"] == 1
    assert result["products"][0]["id"] == str(oldest.pk)
    assert not result["has_more"]
    second = storefront_data(business, page=2)
    assert len(second["products"]) == 2 and not second["has_more"]
    assert not ({p["id"] for p in data["products"]} & {p["id"] for p in second["products"]})


def test_public_search_is_scoped_and_does_not_change_featured(business):
    product = live(business, "Fossil Bag")
    product.category = "Accessories"
    product.description = "Handmade linen bag"
    product.save()
    Product.objects.create(business=business, name="Secret bag", slug="secret")
    alien = Business.objects.create(name="Other", slug="other", country="KE", currency="KES")
    live(alien, "Other bag")
    api = APIClient()
    host = business.domains.get().hostname
    for query in ["bag", "ACCESSORIES", "handmade"]:
        data = api.get("/api/storefront/", {"q": query}, HTTP_HOST=host).json()
        assert data["products_count"] == 1
        assert data["products"][0]["id"] == str(product.pk)
    data = api.get("/api/storefront/", {"q": "unmatched"}, HTTP_HOST=host).json()
    assert data["products"] == [] and data["products_count"] == 0
    assert data["featured_product"]["id"] == str(product.pk)
    assert (
        api.get("/api/storefront/", {"q": "bag"}, HTTP_HOST="unknown.localhost").status_code == 404
    )


def test_preview_search_and_feature_picker_status_filter(client, owner, business):
    login(client, owner)
    published = live(business, "Live bag")
    Product.objects.create(business=business, name="Draft bag", slug="draft")
    data = client.get(f"/api/businesses/{business.pk}/preview/", {"q": "draft"}).json()
    assert data["products_count"] == 1 and data["products"][0]["status"] == "draft"
    assert data["featured_product"]["id"] == str(published.pk)
    picker = client.get(f"/api/businesses/{business.pk}/products/", {"status": "published"}).json()
    assert picker["count"] == 1 and picker["results"][0]["id"] == str(published.pk)
