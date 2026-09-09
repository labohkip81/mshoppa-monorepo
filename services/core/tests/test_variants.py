# Imported pytest fixtures are resolved by name.
# ruff: noqa: F811
import pytest

from apps.catalog.models import Product, Variant
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


def rows():
    return [
        {"label": "Small", "price": "100", "offer_price": "80", "stock": 3},
        {"label": "Large", "price": "150", "stock": 5},
    ]


def test_create_edit_and_soft_remove_variants(client, owner, business):
    login(client, owner)
    url = f"/api/businesses/{business.pk}/products/"
    result = mutate(
        client,
        url,
        {"name": "Shirt", "has_variants": True, "variants": rows(), "status": "published"},
    )
    assert result.status_code == 201, result.data
    product = result.json()
    assert product["has_variants"] and len(product["variants"]) == 2
    first, second = product["variants"]
    changed = [{"id": second["id"], "label": "Large", "price": "160", "offer_price": "120"}]
    response = mutate(client, url + product["id"] + "/", {"variants": changed}, "patch")
    assert response.status_code == 200, response.data
    saved = response.json()["variants"][0]
    assert saved["id"] == second["id"] and saved["sku"] == second["sku"] and saved["stock"] == 5
    assert Variant.objects.get(pk=first["id"]).is_active is False
    public = client.get("/api/storefront/", HTTP_HOST=business.domains.get().hostname).json()
    assert len(public["products"][0]["variants"]) == 1
    assert (
        mutate(client, url + product["id"] + "/", {"description": "Updated"}, "patch").status_code
        == 200
    )


@pytest.mark.parametrize(
    "variants",
    [
        [],
        [{"label": "Bad", "price": "10", "offer_price": "10"}],
        [{"label": "Bad", "price": "-1"}],
        [{"label": "Same", "price": "10"}, {"label": "same", "price": "20"}],
        [{"label": "", "price": "10"}],
        [{"label": "Missing price"}],
    ],
)
def test_invalid_variants_fail_atomically(client, owner, business, variants):
    login(client, owner)
    assert (
        mutate(
            client,
            f"/api/businesses/{business.pk}/products/",
            {"name": "Bad", "has_variants": True, "variants": variants},
        ).status_code
        == 400
    )
    assert not Product.objects.filter(business=business).exists()


def test_switch_single_and_multiple_preserves_original_sku(client, owner, business):
    login(client, owner)
    base = f"/api/businesses/{business.pk}/products/"
    saved = mutate(client, base, {"name": "Switch", "price": "50", "stock": 2}).json()
    row = saved["variants"][0]
    url = base + saved["id"] + "/"
    multi = mutate(
        client,
        url,
        {
            "has_variants": True,
            "variants": [
                {"id": row["id"], "label": "One", "price": "50"},
                {"label": "Two", "price": "70", "stock": 4},
            ],
        },
        "patch",
    )
    assert multi.status_code == 200
    assert multi.json()["variants"][0]["sku"] == row["sku"]
    single = mutate(
        client,
        url,
        {"has_variants": False, "price": "60", "offer_price": None, "stock": 2},
        "patch",
    )
    assert single.status_code == 200 and len(single.json()["variants"]) == 1
    assert single.json()["variants"][0]["sku"] == row["sku"]
    assert Variant.objects.filter(product_id=saved["id"]).count() == 2


def test_foreign_ids_duplicate_ids_and_incomplete_patch_rejected(client, owner, business):
    login(client, owner)
    base = f"/api/businesses/{business.pk}/products/"
    products = [
        mutate(client, base, {"name": name, "has_variants": True, "variants": rows()}).json()
        for name in ["First", "Second"]
    ]
    url = base + products[0]["id"] + "/"
    foreign = {"id": products[1]["variants"][0]["id"], "label": "Foreign", "price": "10"}
    assert mutate(client, url, {"variants": [foreign]}, "patch").status_code == 400
    own = {**foreign, "id": products[0]["variants"][0]["id"]}
    assert (
        mutate(client, url, {"variants": [own, {**own, "label": "Another"}]}, "patch").status_code
        == 400
    )
    assert mutate(client, url, {"variants": [{"id": own["id"]}]}, "patch").status_code == 400
    assert len(client.get(url).json()["variants"]) == 2


def test_variant_currency_and_flag_validation(client, owner, business):
    login(client, owner)
    business.currency = "UGX"
    business.save()
    base = f"/api/businesses/{business.pk}/products/"
    assert (
        mutate(
            client,
            base,
            {"name": "No", "has_variants": True, "variants": [{"label": "One", "price": "10.50"}]},
        ).status_code
        == 400
    )
    assert mutate(client, base, {"name": "No", "has_variants": True}).status_code == 400
    assert (
        mutate(
            client, base, {"name": "No", "price": "10", "stock": 1, "variants": rows()}
        ).status_code
        == 400
    )
