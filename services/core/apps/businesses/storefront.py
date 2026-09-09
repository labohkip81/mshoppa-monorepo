from django.conf import settings
from django.core import signing
from django.db.models import Case, IntegerField, Min, Q, Value, When
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import Product
from apps.catalog.serializers import ProductSerializer

from .models import AuditEvent, BusinessApplication, Domain, Membership
from .serializers import SettingsSerializer
from .views import authorized_business

PREVIEW_SALT = "mshoppa.storefront.preview.v1"


def storefront_data(business, preview=False, query="", page=1, category="", sort="featured"):
    products = Product.objects.filter(business=business).prefetch_related("variants", "images")
    live_products = products.filter(status="published").order_by("-created_at", "-id")
    selected_id = business.store_settings.featured_product_id
    featured = live_products.filter(pk=selected_id).first() if selected_id else None
    if featured is None:
        featured = live_products.first()
    if not preview:
        products = products.filter(status="published")
    categories = list(
        products.exclude(category="")
        .order_by("category")
        .values_list("category", flat=True)
        .distinct()
    )
    if category:
        products = products.filter(category=category[:80])
    query = query.strip()[:180]
    if query:
        products = products.filter(
            Q(name__icontains=query)
            | Q(category__icontains=query)
            | Q(description__icontains=query)
        )
    if sort in {"price-low", "price-high"}:
        products = products.annotate(
            sort_price=Min(
                Coalesce("variants__offer_price", "variants__price"),
                filter=Q(variants__is_active=True),
            )
        )
        products = products.order_by("sort_price" if sort == "price-low" else "-sort_price", "id")
    elif sort == "name":
        products = products.order_by("name", "id")
    elif sort == "featured" and featured:
        products = products.annotate(
            feature_rank=Case(
                When(pk=featured.pk, then=Value(0)), default=Value(1), output_field=IntegerField()
            )
        ).order_by("feature_rank", "-created_at", "-id")
    else:
        products = products.order_by("-created_at", "-id")
    try:
        page = max(1, int(page))
    except (ValueError, TypeError):
        page = 1
    count = products.count()
    start = (page - 1) * 24
    public_settings = dict(SettingsSerializer(business.store_settings).data)
    # A selected product that later becomes a draft must not leak through public settings.
    public_settings.pop("featured_product", None)
    return {
        "id": str(business.pk),
        "name": business.name,
        "phone": business.store_settings.contact_phone
        or BusinessApplication.objects.filter(business=business, status="approved")
        .values_list("phone", flat=True)
        .first()
        or "",
        "currency": business.currency,
        "preview": preview,
        "settings": public_settings,
        "featured_product": ProductSerializer(featured).data if featured else None,
        "products": ProductSerializer(products[start : start + 24], many=True).data,
        "products_count": count,
        "categories": categories,
        "has_more": start + 24 < count,
    }


class StorePreviewView(APIView):
    @extend_schema(responses={200: {"type": "object"}})
    def get(self, request, business_id):
        business = authorized_business(request, business_id)
        return Response(
            storefront_data(
                business,
                preview=True,
                query=request.query_params.get("q", ""),
                page=request.query_params.get("page", 1),
                category=request.query_params.get("category", ""),
                sort=request.query_params.get("sort", "featured"),
            )
        )


class StorePreviewLinkView(APIView):
    @extend_schema(
        request=None, responses={200: {"type": "object", "properties": {"url": {"type": "string"}}}}
    )
    def post(self, request, business_id):
        business = authorized_business(request, business_id)
        if business.suspended:
            raise PermissionDenied("This store is suspended.")
        domain = get_object_or_404(Domain, business=business, is_primary=True, verified=True)
        token = signing.dumps(
            {"business": str(business.pk), "user": request.user.pk, "host": domain.hostname},
            salt=PREVIEW_SALT,
        )
        url = settings.STOREFRONT_URL_PATTERN.format(hostname=domain.hostname)
        AuditEvent.objects.create(
            actor=request.user,
            business=business,
            action="store.preview_created",
            object_id=str(business.pk),
        )
        return Response({"url": f"{url}/#preview={token}"})


class SignedStorePreviewView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(responses={200: {"type": "object"}})
    def get(self, request):
        try:
            grant = signing.loads(
                request.headers.get("X-Mshoppa-Preview", ""), salt=PREVIEW_SALT, max_age=300
            )
        except signing.BadSignature:
            raise PermissionDenied(
                "This preview link is invalid or has expired. Open a new preview from your workspace."
            )
        hostname = request.get_host().split(":", 1)[0].lower().rstrip(".")
        if hostname != grant["host"]:
            raise PermissionDenied("This preview belongs to a different store address.")
        membership = get_object_or_404(
            Membership.objects.select_related("business__store_settings"),
            business_id=grant["business"],
            user_id=grant["user"],
            user__is_active=True,
            business__suspended=False,
            business__provisioning_status="ready",
        )
        get_object_or_404(Domain, business=membership.business, hostname=hostname, verified=True)
        return Response(
            storefront_data(
                membership.business,
                preview=True,
                query=request.query_params.get("q", ""),
                page=request.query_params.get("page", 1),
                category=request.query_params.get("category", ""),
                sort=request.query_params.get("sort", "featured"),
            )
        )


class PublicStoreView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(responses={200: {"type": "object"}})
    def get(self, request):
        # Resolve only an exact verified host. Unknown hosts never fall back to a store.
        hostname = request.get_host().split(":", 1)[0].lower().rstrip(".")
        domain = get_object_or_404(
            Domain.objects.select_related("business__store_settings"),
            hostname=hostname,
            verified=True,
            business__published=True,
            business__suspended=False,
            business__provisioning_status="ready",
        )
        product = None
        if "product" in request.query_params:
            product = get_object_or_404(
                Product.objects.filter(
                    business=domain.business, status="published"
                ).prefetch_related("variants", "images"),
                slug=request.query_params["product"],
            )
        data = storefront_data(
            domain.business,
            query=request.query_params.get("q", ""),
            page=request.query_params.get("page", 1),
            category=request.query_params.get("category", ""),
            sort=request.query_params.get("sort", "featured"),
        )
        if product:
            data["product"] = ProductSerializer(product).data
        return Response(data)
