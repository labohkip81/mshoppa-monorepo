from django.core import signing
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.views import CsrfAPIView
from apps.catalog.images import normalize_image

from .models import AuditEvent, StoreSettings
from .serializers import SettingsSerializer
from .views import authorized_business


class LogoUploadSerializer(serializers.Serializer):
    image = serializers.FileField()


class StoreLogoView(CsrfAPIView):
    parser_classes = [MultiPartParser, FormParser]
    image_field = "logo"

    @extend_schema(request=LogoUploadSerializer, responses=SettingsSerializer)
    def post(self, request, business_id):
        business = authorized_business(request, business_id, write=True)
        upload = LogoUploadSerializer(data=request.data)
        upload.is_valid(raise_exception=True)
        content, _, _, _ = normalize_image(upload.validated_data["image"])
        with transaction.atomic():
            store = get_object_or_404(StoreSettings, business=business)
            getattr(store, self.image_field).save(f"{self.image_field}.webp", content, save=True)
            AuditEvent.objects.create(
                actor=request.user,
                business=business,
                action=f"store.{self.image_field}_updated",
                object_id=str(business.pk),
            )
        return Response(SettingsSerializer(store).data)

    @extend_schema(responses=SettingsSerializer)
    def delete(self, request, business_id):
        business = authorized_business(request, business_id, write=True)
        with transaction.atomic():
            store = get_object_or_404(StoreSettings, business=business)
            # Retain the old local file for recovery; its signed URL stops working.
            setattr(store, self.image_field, "")
            store.save(update_fields=[self.image_field])
            AuditEvent.objects.create(
                actor=request.user,
                business=business,
                action=f"store.{self.image_field}_removed",
                object_id=str(business.pk),
            )
        return Response(SettingsSerializer(store).data)


class StoreLogoContentView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    image_field = "logo"

    @extend_schema(responses={(200, "image/webp"): bytes})
    def get(self, request, business_id):
        try:
            name = signing.TimestampSigner(salt=f"mshoppa.store.{self.image_field}.v1").unsign(
                request.query_params.get("token", ""), max_age=3600
            )
        except signing.BadSignature:
            raise PermissionDenied("This image link is invalid or has expired.")
        store = get_object_or_404(StoreSettings, business_id=business_id, business__suspended=False)
        stored_image = getattr(store, self.image_field)
        if not stored_image or stored_image.name != name:
            raise Http404("Image not found.")
        try:
            file = stored_image.open("rb")
        except FileNotFoundError:
            raise Http404("Image not found.")
        response = FileResponse(file, content_type="image/webp")
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "default-src 'none'"
        return response


class StoreCoverView(StoreLogoView):
    image_field = "cover"


class StoreCoverContentView(StoreLogoContentView):
    image_field = "cover"
