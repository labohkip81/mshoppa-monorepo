from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.accounts.views import CsrfAPIView, PlatformPermission

from .management_api import BusinessNameSerializer
from .models import AuditEvent, Business, BusinessApplication, Membership, StoreSettings
from .serializers import (
    ApplicationSerializer,
    BusinessSerializer,
    ReviewSerializer,
    SettingsSerializer,
)
from .services import review_application


class ApplicationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ApplicationSerializer
    queryset = BusinessApplication.objects.none()
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return BusinessApplication.objects.none()
        return BusinessApplication.objects.filter(owner=self.request.user).select_related(
            "owner", "business"
        )

    def perform_create(self, serializer):
        if not self.request.user.email_verified:
            raise PermissionDenied("Verify your email before applying.")
        try:
            with transaction.atomic():
                serializer.save(owner=self.request.user)
        except IntegrityError:
            raise ValidationError({"slug": "This store address is already taken."})

    def perform_update(self, serializer):
        with transaction.atomic():
            application = self.get_queryset().get(pk=serializer.instance.pk)
            if application.status not in ("draft", "changes_requested"):
                raise ValidationError(
                    "This application cannot be edited while under review or after a decision."
                )
            serializer.instance = application
            serializer.save()

    @extend_schema(request=None, responses=ApplicationSerializer)
    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        with transaction.atomic():
            application = self.get_object()
            if application.status == "pending":
                return Response(self.get_serializer(application).data)
            if application.status not in ("draft", "changes_requested"):
                raise ValidationError("This application cannot be submitted.")
            application.status = "pending"
            application.submitted_at = timezone.now()
            application.save(update_fields=["status", "submitted_at", "updated_at"])
        return Response(self.get_serializer(application).data)


class PlatformApplicationViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    serializer_class = ApplicationSerializer
    permission_classes = [PlatformPermission]

    def get_queryset(self):
        queryset = BusinessApplication.objects.exclude(status="draft").select_related(
            "owner", "business"
        )
        status = self.request.query_params.get("status")
        return queryset.filter(status=status) if status else queryset

    @extend_schema(request=ReviewSerializer, responses=ApplicationSerializer)
    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        application = self.get_object()
        serializer = ReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = review_application(application.pk, request.user, **serializer.validated_data)
        return Response(self.get_serializer(updated).data)

    @extend_schema(request=None, responses=ApplicationSerializer)
    @action(detail=True, methods=["post"], url_path="retry-provisioning")
    def retry_provisioning(self, request, pk=None):
        with transaction.atomic():
            application = self.get_object()
            if application.status != "approved" or not application.business_id:
                raise ValidationError("Approve this application before provisioning.")
            if application.business.provisioning_status == "failed":
                Business.objects.filter(pk=application.business_id).update(
                    provisioning_status="queued", provisioning_error=""
                )
                AuditEvent.objects.create(
                    actor=request.user,
                    business_id=application.business_id,
                    action="business.provisioning_retried",
                    object_id=str(application.business_id),
                )
        application.refresh_from_db()
        return Response(self.get_serializer(application).data)


class BusinessViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = BusinessSerializer
    queryset = Business.objects.none()

    @extend_schema(request=BusinessNameSerializer, responses=BusinessSerializer)
    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        from .management_api import BusinessNameSerializer, access, audit

        business = access(request, kwargs["pk"], ["owner", "manager"])
        data = BusinessNameSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        business.name = data.validated_data["name"]
        business.save(update_fields=["name"])
        audit(request, business, "business.renamed", business.pk)
        return Response(self.get_serializer(business).data)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Business.objects.none()
        return (
            Business.objects.filter(memberships__user=self.request.user)
            .prefetch_related("domains", "memberships")
            .order_by("name")
        )


def authorized_business(request, business_id, write=False):
    membership = get_object_or_404(
        Membership.objects.select_related("business"), user=request.user, business_id=business_id
    )
    if membership.business.provisioning_status != "ready":
        raise ValidationError("Your store is still being prepared.")
    if write and membership.business.suspended:
        raise PermissionDenied("This store is suspended. Contact MSHOPPA support.")
    if write and membership.role not in ("owner", "manager"):
        raise PermissionDenied("Your role does not allow this change.")
    return membership.business


class BusinessSettingsView(CsrfAPIView):
    @extend_schema(responses=SettingsSerializer)
    def get(self, request, business_id):
        business = authorized_business(request, business_id)
        return Response(
            SettingsSerializer(get_object_or_404(StoreSettings, business=business)).data
        )

    @extend_schema(request=SettingsSerializer, responses=SettingsSerializer)
    def patch(self, request, business_id):
        business = authorized_business(request, business_id, write=True)
        serializer = SettingsSerializer(
            get_object_or_404(StoreSettings, business=business), data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            serializer.save()
            AuditEvent.objects.create(
                actor=request.user,
                business=business,
                action="store.settings_updated",
                object_id=str(business.pk),
            )
        return Response(serializer.data)
