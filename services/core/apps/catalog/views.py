import uuid

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.text import slugify
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.businesses.models import AuditEvent
from apps.businesses.views import authorized_business

from .images import normalize_image
from .models import Product, ProductImage, Variant
from .serializers import (
    ProductCreateSerializer,
    ProductImageSerializer,
    ProductImageUploadSerializer,
    ProductSerializer,
)


class ProductViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ProductSerializer
    queryset = Product.objects.none()
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Product.objects.none()
        business = authorized_business(self.request, self.kwargs["business_id"])
        queryset = Product.objects.filter(business=business).prefetch_related("variants", "images")
        search = self.request.query_params.get("search", "").strip()[:150]
        status = self.request.query_params.get("status")
        if status in {"draft", "published"}:
            queryset = queryset.filter(status=status)
        return queryset.filter(name__icontains=search) if search else queryset

    def get_serializer_class(self):
        return (
            ProductCreateSerializer
            if self.action in {"create", "partial_update"}
            else ProductSerializer
        )

    @extend_schema(request=ProductCreateSerializer, responses={201: ProductSerializer})
    def create(self, request, *args, **kwargs):
        from rest_framework.response import Response

        business = authorized_business(request, kwargs["business_id"], write=True)
        serializer = ProductCreateSerializer(
            data=request.data, context={"currency": business.currency}
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data.copy()
        rows = data.pop("variants", None)
        price, stock, offer = (
            data.pop("price", None),
            data.pop("stock", 0),
            data.pop("offer_price", None),
        )
        with transaction.atomic():
            suffix = uuid.uuid4().hex[:8]
            product = Product.objects.create(
                business=business,
                slug=f"{slugify(data['name'])[:160] or 'product'}-{suffix}",
                **data,
            )
            if product.has_variants:
                self.save_variants(product, rows)
            else:
                Variant.objects.create(
                    product=product,
                    sku=f"SKU-{suffix.upper()}",
                    price=price,
                    stock=stock,
                    offer_price=offer,
                )
            AuditEvent.objects.create(
                actor=request.user,
                business=business,
                action="product.created",
                object_id=str(product.pk),
                detail={
                    "initial_stock": sum(v.stock for v in product.variants.filter(is_active=True))
                },
            )
        return Response(ProductSerializer(product).data, status=201)

    @extend_schema(request=ProductCreateSerializer, responses=ProductSerializer)
    def partial_update(self, request, *args, **kwargs):
        with transaction.atomic():
            business = authorized_business(request, kwargs["business_id"], write=True)
            product = get_object_or_404(Product, business=business, pk=kwargs["pk"])
            variant = product.variants.filter(is_active=True).first()
            serializer = ProductCreateSerializer(
                data=request.data,
                partial=True,
                context={"currency": business.currency, "variant": variant, "product": product},
            )
            serializer.is_valid(raise_exception=True)
            previous_stock = sum(v.stock for v in product.variants.filter(is_active=True))
            data = serializer.validated_data
            for field in ("name", "category", "description", "status", "has_variants"):
                if field in data:
                    setattr(product, field, data[field])
            product.save()
            if product.has_variants:
                if "variants" in data:
                    self.save_variants(product, data["variants"])
            else:
                if variant is None:
                    variant = Variant(product=product, sku=f"SKU-{uuid.uuid4().hex[:12].upper()}")
                for field in ("price", "offer_price", "stock"):
                    if field in data:
                        setattr(variant, field, data[field])
                variant.label = "Default"
                variant.position = 0
                variant.is_active = True
                variant.save()
                product.variants.exclude(pk=variant.pk).update(is_active=False)
            AuditEvent.objects.create(
                actor=request.user,
                business=business,
                action="product.updated",
                object_id=str(product.pk),
                detail={
                    "fields": list(data),
                    "previous_stock": previous_stock,
                    "stock": sum(v.stock for v in product.variants.filter(is_active=True)),
                },
            )
        return Response(ProductSerializer(product).data)

    @staticmethod
    def save_variants(product, rows):
        existing = {variant.pk: variant for variant in product.variants.all()}
        active_ids = []
        for position, row in enumerate(rows):
            variant = existing.get(row.get("id")) or Variant(
                product=product, sku=f"SKU-{uuid.uuid4().hex[:12].upper()}"
            )
            variant.label = row["label"]
            variant.price = row["price"]
            variant.offer_price = row.get("offer_price")
            variant.stock = row.get("stock", variant.stock or 0)
            variant.position = position
            variant.is_active = True
            variant.save()
            active_ids.append(variant.pk)
        # Preserve removed rows/SKUs for recovery and future order references.
        product.variants.exclude(pk__in=active_ids).update(is_active=False)

    @extend_schema(request=ProductImageUploadSerializer, responses={201: ProductImageSerializer})
    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def images(self, request, business_id=None, pk=None):
        business = authorized_business(request, business_id, write=True)
        product = get_object_or_404(Product, business=business, pk=pk)
        serializer = ProductImageUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        content, width, height, name = normalize_image(serializer.validated_data["image"])
        with transaction.atomic():
            authorized_business(request, business_id, write=True)
            if product.images.count() >= 8:
                raise ValidationError(
                    {
                        "image": "A product can have up to 8 images. Remove one before adding another."
                    }
                )
            image = ProductImage(product=product, original_name=name, width=width, height=height)
            image.file.save("image.webp", content, save=False)
            image.save()
            AuditEvent.objects.create(
                actor=request.user,
                business=business,
                action="product.image_uploaded",
                object_id=str(image.pk),
                detail={"product": str(product.pk)},
            )
        return Response(ProductImageSerializer(image).data, status=201)

    @extend_schema(request=None, responses={204: None})
    @action(detail=True, methods=["delete"], url_path=r"images/(?P<image_id>[0-9a-f-]+)")
    def remove_image(self, request, business_id=None, pk=None, image_id=None):
        with transaction.atomic():
            business = authorized_business(request, business_id, write=True)
            image = get_object_or_404(
                ProductImage, pk=image_id, product_id=pk, product__business=business
            )
            image.delete()
            # Retain the local file for recovery; it is no longer served without its DB record.
            AuditEvent.objects.create(
                actor=request.user,
                business=business,
                action="product.image_removed",
                object_id=str(image_id),
                detail={"product": str(pk)},
            )
        return Response(status=204)
