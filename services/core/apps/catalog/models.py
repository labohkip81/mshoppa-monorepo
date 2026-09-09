import uuid

from django.db import models

from apps.businesses.models import Business


class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="products")
    name = models.CharField(max_length=180)
    slug = models.SlugField(max_length=180)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=80, blank=True)
    has_variants = models.BooleanField(default=False)
    status = models.CharField(
        max_length=12, default="draft", choices=[("draft", "Draft"), ("published", "Published")]
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["business", "slug"], name="product_slug_per_business")
        ]


class Variant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    sku = models.CharField(max_length=80)
    label = models.CharField(max_length=120, default="Default")
    price = models.DecimalField(max_digits=12, decimal_places=2)
    offer_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    stock = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(fields=["product", "sku"], name="sku_per_product"),
            models.CheckConstraint(
                condition=models.Q(price__gte=0), name="variant_price_nonnegative"
            ),
            models.CheckConstraint(
                condition=models.Q(offer_price__isnull=True)
                | (models.Q(offer_price__gte=0) & models.Q(offer_price__lt=models.F("price"))),
                name="variant_offer_below_price",
            ),
        ]


def product_image_path(instance, filename):
    return f"products/{instance.product.business_id}/{instance.product_id}/{instance.id}.webp"


class ProductImage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    file = models.FileField(upload_to=product_image_path)
    original_name = models.CharField(max_length=180)
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
