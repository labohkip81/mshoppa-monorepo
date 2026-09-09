import warnings
from io import BytesIO
from pathlib import Path

from django.core import signing
from django.core.files.base import ContentFile
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from .models import ProductImage
from .serializers import IMAGE_SALT

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000


def normalize_image(upload):
    """Decode actual pixels, strip metadata, and store a bounded WebP, never raw uploads."""
    if upload.size > MAX_IMAGE_BYTES:
        raise ValidationError({"image": "Each image must be 5 MB or smaller."})
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(upload) as source:
                if source.format not in {"JPEG", "PNG", "WEBP"}:
                    raise ValidationError({"image": "Choose a JPEG, PNG or WebP image."})
                if source.width * source.height > MAX_IMAGE_PIXELS:
                    raise ValidationError(
                        {"image": "Image dimensions must not exceed 20 megapixels."}
                    )
                if getattr(source, "is_animated", False):
                    raise ValidationError({"image": "Use a still image, not an animation."})
                source.load()
                normalized = ImageOps.exif_transpose(source).convert("RGBA")
                normalized.thumbnail((2000, 2000), Image.Resampling.LANCZOS)
                # Fresh pixels avoid retaining EXIF, location, ICC or text metadata.
                clean = Image.new("RGBA", normalized.size)
                clean.paste(normalized)
                output = BytesIO()
                clean.save(output, format="WEBP", quality=85, method=4)
                return (
                    ContentFile(output.getvalue(), name="image.webp"),
                    clean.width,
                    clean.height,
                    Path(upload.name).name[:180],
                )
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise ValidationError(
            {"image": "This image could not be read. Choose a valid JPEG, PNG or WebP file."}
        )


class ProductImageContentView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(responses={(200, "image/webp"): bytes})
    def get(self, request, image_id):
        try:
            signed_id = signing.TimestampSigner(salt=IMAGE_SALT).unsign(
                request.query_params.get("token", ""), max_age=3600
            )
        except signing.BadSignature:
            raise PermissionDenied("This image link has expired or is invalid. Refresh the page.")
        if signed_id != str(image_id):
            raise PermissionDenied("This image link belongs to a different image.")
        image = get_object_or_404(ProductImage, pk=image_id, product__business__suspended=False)
        try:
            file = image.file.open("rb")
        except FileNotFoundError:
            raise Http404("Image file not found.")
        response = FileResponse(file, content_type="image/webp")
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "default-src 'none'"
        return response
