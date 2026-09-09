from decimal import Decimal

from django.core import signing
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.rich_text import RichTextField

from .models import Product, ProductImage, Variant

IMAGE_SALT = "mshoppa.catalog.image.v1"


class ProductImageSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    def get_url(self, obj) -> str:
        token = signing.TimestampSigner(salt=IMAGE_SALT).sign(str(obj.pk))
        return f"/api/product-images/{obj.pk}/content/?token={token}"

    class Meta:
        model = ProductImage
        fields = ["id", "url", "original_name", "width", "height"]
        read_only_fields = fields


class VariantSerializer(serializers.ModelSerializer):
    price = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"))

    class Meta:
        model = Variant
        fields = ["id", "sku", "label", "price", "offer_price", "stock"]
        read_only_fields = ["id"]


class ProductSerializer(serializers.ModelSerializer):
    description = RichTextField(10000, required=False, allow_blank=True)
    variants = serializers.SerializerMethodField()
    images = ProductImageSerializer(many=True, read_only=True)

    @extend_schema_field(VariantSerializer(many=True))
    def get_variants(self, obj):
        return VariantSerializer(
            [variant for variant in obj.variants.all() if variant.is_active], many=True
        ).data

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "category",
            "status",
            "has_variants",
            "variants",
            "images",
            "created_at",
        ]
        read_only_fields = ["id", "slug", "created_at"]


class VariantInputSerializer(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    label = serializers.CharField(max_length=120)
    price = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"))
    offer_price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0"),
        required=False,
        allow_null=True,
        default=None,
    )
    stock = serializers.IntegerField(min_value=0, max_value=1000000, required=False)


class ProductCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=180)
    status = serializers.ChoiceField(
        choices=["draft", "published"], required=False, default="draft"
    )
    category = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    description = RichTextField(10000, required=False, allow_blank=True, default="")
    has_variants = serializers.BooleanField(required=False)
    variants = VariantInputSerializer(many=True, required=False, allow_empty=False, max_length=50)
    price = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False
    )
    offer_price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0"),
        required=False,
        allow_null=True,
        default=None,
    )
    stock = serializers.IntegerField(min_value=0, max_value=1000000, required=False)

    def validate(self, data):
        product = self.context.get("product")
        multiple = data.get("has_variants", product.has_variants if product else False)
        if multiple:
            if (
                any(field in data for field in ("price", "stock"))
                or data.get("offer_price") is not None
            ):
                raise serializers.ValidationError(
                    "Set prices and quantities on each variant, not the product."
                )
            if "variants" not in data and (not product or not product.has_variants):
                raise serializers.ValidationError({"variants": "Add at least one variant."})
            existing_ids = set(product.variants.values_list("id", flat=True)) if product else set()
            labels, ids = set(), set()
            for index, variant in enumerate(data.get("variants", [])):
                if "label" not in variant or "price" not in variant:
                    raise serializers.ValidationError(
                        {"variants": f"Variant {index + 1}: name and price are required."}
                    )
                label = variant["label"].casefold()
                if label in labels:
                    raise serializers.ValidationError(
                        {"variants": f"Variant {index + 1}: use a unique name."}
                    )
                labels.add(label)
                variant_id = variant.get("id")
                if variant_id and (variant_id not in existing_ids or variant_id in ids):
                    raise serializers.ValidationError(
                        {"variants": f"Variant {index + 1}: invalid or repeated variant ID."}
                    )
                ids.add(variant_id)
                self.validate_prices(
                    variant["price"], variant.get("offer_price"), f"variants.{index + 1}."
                )
            return data
        if "variants" in data:
            raise serializers.ValidationError(
                {"variants": "Enable Has variants before adding variant options."}
            )
        if not product or product.has_variants or not self.context.get("variant"):
            missing = {
                field: "This field is required for a single-price product."
                for field in ("price", "stock")
                if field not in data
            }
            if missing:
                raise serializers.ValidationError(missing)
        variant = self.context.get("variant")
        price = data.get("price", variant.price if variant else None)
        offer = data.get("offer_price", variant.offer_price if variant else None)
        self.validate_prices(price, offer)
        return data

    def validate_prices(self, price, offer, prefix=""):
        if offer is not None and (price is None or offer >= price):
            raise serializers.ValidationError(
                {
                    prefix
                    + "offer_price": "Offer price must be lower than the regular price. Clear it to remove the offer."
                }
            )
        if self.context.get("currency") in {"UGX", "RWF"}:
            for field, value in (("price", price), ("offer_price", offer)):
                if value is not None and value != value.to_integral_value():
                    raise serializers.ValidationError(
                        {prefix + field: "This currency requires whole-unit prices."}
                    )


class ProductImageUploadSerializer(serializers.Serializer):
    image = serializers.FileField()
