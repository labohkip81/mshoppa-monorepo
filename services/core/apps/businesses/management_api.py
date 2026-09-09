"""Store-scoped operations for the merchant workspace."""

import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Count, Max, Q, Sum
from django.db.models.functions import Lower
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.checkout.models import Order, OrderLine

from .models import AuditEvent, Business, Domain, Membership
from .serializers import RESERVED


def access(request, business_id, roles=None):
    membership = get_object_or_404(
        Membership.objects.select_related("business"), business_id=business_id, user=request.user
    )
    if roles and membership.role not in roles:
        raise PermissionDenied("Your role does not allow this action.")
    if request.method not in ("GET", "HEAD", "OPTIONS") and membership.business.suspended:
        raise PermissionDenied("This store is suspended.")
    return membership.business


def audit(request, business, action, object_id):
    AuditEvent.objects.create(
        actor=request.user, business=business, action=action, object_id=str(object_id)
    )


class StoreScopedViewSet(viewsets.GenericViewSet):
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def business(self, roles=None):
        return access(self.request, self.kwargs["business_id"], roles)


class OrderLineAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderLine
        fields = ["id", "product_name", "variant_name", "quantity", "unit_price", "line_total"]


class MerchantOrderSerializer(serializers.ModelSerializer):
    lines = OrderLineAdminSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "customer_name",
            "email",
            "phone",
            "address",
            "currency",
            "subtotal",
            "tax",
            "total",
            "provider",
            "status",
            "created_at",
            "fulfillment_status",
            "staff_notes",
            "tracking_reference",
            "lines",
        ]
        read_only_fields = fields


class FulfillmentSerializer(serializers.Serializer):
    fulfillment_status = serializers.ChoiceField(
        choices=["unfulfilled", "processing", "shipped", "delivered"], required=False
    )
    staff_notes = serializers.CharField(max_length=4000, allow_blank=True, required=False)
    tracking_reference = serializers.CharField(max_length=200, allow_blank=True, required=False)


class MerchantOrderViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, StoreScopedViewSet):
    serializer_class = MerchantOrderSerializer
    queryset = Order.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()
        business = self.business()
        rows = (
            Order.objects.filter(business=business)
            .prefetch_related("lines")
            .order_by("-created_at", "-id")
        )
        query = self.request.query_params.get("q", "").strip()[:150]
        if query:
            rows = rows.filter(
                Q(email__icontains=query)
                | Q(customer_name__icontains=query)
                | Q(id__icontains=query)
            )
        for field in ["status", "fulfillment_status"]:
            value = self.request.query_params.get(field)
            if value:
                rows = rows.filter(**{field: value})
        if email := self.request.query_params.get("email"):
            rows = rows.filter(email__iexact=email)
        return rows

    @extend_schema(request=FulfillmentSerializer, responses=MerchantOrderSerializer)
    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        business = self.business(["owner", "manager", "fulfillment"])
        order = self.get_object()
        data = FulfillmentSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        new_status = data.validated_data.get("fulfillment_status", order.fulfillment_status)
        if new_status != "unfulfilled" and order.status != "paid":
            raise ValidationError("Only paid orders can be fulfilled.")
        sequence = ["unfulfilled", "processing", "shipped", "delivered"]
        if sequence.index(new_status) < sequence.index(order.fulfillment_status):
            raise ValidationError("Fulfillment cannot move backwards.")
        for key, value in data.validated_data.items():
            setattr(order, key, value)
        order.save(update_fields=list(data.validated_data))
        audit(request, business, "order.fulfillment_updated", order.pk)
        return Response(self.get_serializer(order).data)


class MerchantPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = [
            "id",
            "customer_name",
            "email",
            "provider",
            "status",
            "total",
            "currency",
            "session_id",
            "payment_backend",
            "payment_review_required",
            "created_at",
        ]
        read_only_fields = fields


class MerchantPaymentViewSet(mixins.ListModelMixin, StoreScopedViewSet):
    @extend_schema(responses={200: {"type": "object"}})
    @action(detail=False, methods=['get'])
    def providers(self, request, business_id=None):
        self.business(['owner', 'manager'])
        from apps.checkout.protocol import signed_post
        try:
            return Response(signed_post(settings.PAYMENT_SERVICE_URL + '/api/providers/', {'business_id': str(business_id)}))
        except (OSError, ValueError):
            return Response({'detail': 'The payment service is unavailable.'}, status=503)

    serializer_class = MerchantPaymentSerializer
    queryset = Order.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()
        rows = Order.objects.filter(business=self.business(["owner", "manager"])).order_by(
            "-created_at", "-id"
        )
        if status := self.request.query_params.get("status"):
            rows = rows.filter(status=status)
        if provider := self.request.query_params.get("provider"):
            rows = rows.filter(provider=provider)
        return rows


class CustomerSerializer(serializers.Serializer):
    email = serializers.EmailField(source="customer_email")
    order_count = serializers.IntegerField()
    paid_total = serializers.DecimalField(max_digits=18, decimal_places=2)
    last_order = serializers.DateTimeField()


class MerchantCustomerViewSet(mixins.ListModelMixin, StoreScopedViewSet):
    serializer_class = CustomerSerializer
    queryset = Order.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()
        rows = Order.objects.filter(business=self.business())
        if query := self.request.query_params.get("q", "").strip()[:150]:
            rows = rows.filter(email__icontains=query)
        return (
            rows.annotate(customer_email=Lower("email"))
            .values("customer_email")
            .annotate(
                order_count=Count("id"),
                paid_total=Sum("total", filter=Q(status="paid"), default=0),
                last_order=Max("created_at"),
            )
            .order_by("-last_order", "customer_email")
        )


class BusinessNameSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)


class DomainAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = Domain
        fields = ["id", "hostname", "verified", "is_primary"]
        read_only_fields = ["id", "verified", "is_primary"]
        extra_kwargs = {"hostname": {"validators": []}}

    def validate_hostname(self, value):
        value = value.strip().lower().rstrip(".")
        if not settings.DEBUG or settings.BASE_DOMAIN != "localhost":
            raise serializers.ValidationError(
                "Adding domains is currently available only for local development."
            )
        if (
            not re.fullmatch(r"[a-z][a-z0-9-]{1,48}[a-z0-9]\.localhost", value)
            or value.split(".")[0] in RESERVED
        ):
            raise serializers.ValidationError(
                "Use an available shop-name.localhost address (3–50 letters, numbers or hyphens)."
            )
        slug = value.removesuffix(".localhost")
        from .models import BusinessApplication

        business = self.context["business"]
        if (
            BusinessApplication.objects.filter(slug=slug).exclude(business=business).exists()
            or Business.objects.filter(slug=slug).exclude(pk=business.pk).exists()
        ):
            raise serializers.ValidationError("This address is reserved for another store.")
        return value


class DomainPrimarySerializer(serializers.Serializer):
    is_primary = serializers.BooleanField()

    def validate_is_primary(self, value):
        if not value:
            raise serializers.ValidationError("Select another domain as primary instead.")
        return value


class MerchantDomainViewSet(mixins.ListModelMixin, StoreScopedViewSet):
    serializer_class = DomainAdminSerializer
    queryset = Domain.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Domain.objects.none()
        return Domain.objects.filter(business=self.business()).order_by("-is_primary", "hostname")

    @extend_schema(request=DomainAdminSerializer, responses={201: DomainAdminSerializer})
    def create(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                business = self.business(["owner", "manager"])
                data = self.get_serializer(data=request.data, context={"business": business})
                data.is_valid(raise_exception=True)
                domain = data.save(
                    business=business,
                    verified=True,
                    is_primary=not business.domains.filter(is_primary=True).exists(),
                )
                audit(request, business, "domain.added", domain.pk)
                return Response(self.get_serializer(domain).data, status=201)
        except IntegrityError:
            raise ValidationError({"hostname": "This domain is already in use."})

    @extend_schema(request=DomainPrimarySerializer, responses=DomainAdminSerializer)
    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        business = self.business(["owner", "manager"])
        domain = self.get_object()
        data = DomainPrimarySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        if not domain.verified:
            raise ValidationError("Verify this domain before using it as primary.")
        business.domains.update(is_primary=False)
        domain.is_primary = True
        domain.save(update_fields=["is_primary"])
        audit(request, business, "domain.primary_changed", domain.pk)
        return Response(self.get_serializer(domain).data)

    @extend_schema(responses={204: None})
    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        business = self.business(["owner", "manager"])
        domain = self.get_object()
        if domain.is_primary:
            raise ValidationError("Choose another primary domain before removing this one.")
        audit(request, business, "domain.removed", domain.pk)
        domain.delete()
        return Response(status=204)


class StaffSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    name = serializers.CharField(source="user.first_name", read_only=True)
    user_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "user_id", "email", "name", "role"]
        read_only_fields = fields


class StaffAddSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=Membership._meta.get_field("role").choices)


class StaffRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=Membership._meta.get_field("role").choices)


class MerchantStaffViewSet(mixins.ListModelMixin, StoreScopedViewSet):
    serializer_class = StaffSerializer
    queryset = Membership.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Membership.objects.none()
        return (
            Membership.objects.filter(business=self.business(["owner"]))
            .select_related("user")
            .order_by("user__email")
        )

    @extend_schema(request=StaffAddSerializer, responses={201: StaffSerializer})
    def create(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                business = self.business(["owner"])
                data = StaffAddSerializer(data=request.data)
                data.is_valid(raise_exception=True)
                user = (
                    get_user_model()
                    .objects.filter(
                        email__iexact=data.validated_data["email"],
                        is_active=True,
                        email_verified=True,
                        is_staff=False,
                        is_superuser=False,
                    )
                    .first()
                )
                if not user:
                    raise ValidationError(
                        {
                            "email": "Use an existing, verified business account. Ask this person to sign up and verify their email first."
                        }
                    )
                member = Membership.objects.create(
                    business=business, user=user, role=data.validated_data["role"]
                )
                audit(request, business, "staff.added", member.pk)
                return Response(self.get_serializer(member).data, status=201)
        except IntegrityError:
            raise ValidationError("This person already has access to this store.")

    def protect_owner(self, member):
        if member.user_id == self.request.user.pk:
            raise ValidationError("Another owner must change or remove your own access.")
        if (
            member.role == "owner"
            and not Membership.objects.filter(
                business=member.business, role="owner", user__is_active=True
            )
            .exclude(pk=member.pk)
            .exists()
        ):
            raise ValidationError("Keep at least one active owner for this store.")

    @extend_schema(request=StaffRoleSerializer, responses=StaffSerializer)
    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        business = self.business(["owner"])
        member = self.get_object()
        self.protect_owner(member)
        data = StaffRoleSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        member.role = data.validated_data["role"]
        member.save(update_fields=["role"])
        audit(request, business, "staff.role_changed", member.pk)
        return Response(self.get_serializer(member).data)

    @extend_schema(responses={204: None})
    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        business = self.business(["owner"])
        member = self.get_object()
        self.protect_owner(member)
        audit(request, business, "staff.removed", member.pk)
        member.delete()
        return Response(status=204)


class PromotionSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_status = serializers.CharField(source="product.status", read_only=True)

    class Meta:
        from apps.catalog.models import Variant

        model = Variant
        fields = ["id", "product_name", "product_status", "label", "price", "offer_price"]
        read_only_fields = fields


class OfferSerializer(serializers.Serializer):
    offer_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=0, allow_null=True
    )


class MerchantPromotionViewSet(mixins.ListModelMixin, StoreScopedViewSet):
    from apps.catalog.models import Variant

    serializer_class = PromotionSerializer
    queryset = Variant.objects.none()

    def get_queryset(self):
        from apps.catalog.models import Variant

        if getattr(self, "swagger_fake_view", False):
            return Variant.objects.none()
        rows = (
            Variant.objects.filter(product__business=self.business(), is_active=True)
            .select_related("product")
            .order_by("product__name", "label", "id")
        )
        if query := self.request.query_params.get("q", "").strip()[:150]:
            rows = rows.filter(Q(product__name__icontains=query) | Q(label__icontains=query))
        if self.request.query_params.get("active") == "true":
            rows = rows.filter(offer_price__isnull=False)
        return rows

    @extend_schema(request=OfferSerializer, responses=PromotionSerializer)
    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        business = self.business(["owner", "manager"])
        variant = self.get_object()
        data = OfferSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        offer = data.validated_data["offer_price"]
        if offer is not None and offer >= variant.price:
            raise ValidationError(
                {"offer_price": "Offer price must be lower than the regular price."}
            )
        if (
            offer is not None
            and business.currency in {"UGX", "RWF"}
            and offer != offer.to_integral_value()
        ):
            raise ValidationError({"offer_price": "This currency requires whole-unit prices."})
        variant.offer_price = offer
        variant.save(update_fields=["offer_price"])
        audit(request, business, "promotion.updated", variant.pk)
        return Response(self.get_serializer(variant).data)
