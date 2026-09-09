import re
from urllib.parse import quote, urlsplit

from django.conf import settings
from django.core import signing
from rest_framework import serializers

from apps.catalog.models import Product
from apps.rich_text import RichTextField

from .models import Business, BusinessApplication, Domain, StoreSettings

RESERVED = {
    "admin",
    "platform",
    "payments",
    "storage",
    "www",
    "api",
    "mail",
    "support",
    "account",
    "accounts",
    "static",
    "assets",
    "app",
    "mshoppa",
}


class ApplicationSerializer(serializers.ModelSerializer):
    owner_email = serializers.EmailField(source="owner.email", read_only=True)
    provisioning_status = serializers.CharField(
        source="business.provisioning_status", read_only=True, default=None
    )

    class Meta:
        model = BusinessApplication
        fields = [
            "id",
            "name",
            "slug",
            "category",
            "phone",
            "country",
            "currency",
            "description",
            "status",
            "review_note",
            "submitted_at",
            "reviewed_at",
            "created_at",
            "owner_email",
            "business",
            "provisioning_status",
        ]
        read_only_fields = [
            "id",
            "status",
            "review_note",
            "submitted_at",
            "reviewed_at",
            "created_at",
            "business",
        ]

    def validate_slug(self, value):
        value = value.lower().strip()
        if value in RESERVED or not re.fullmatch(r"[a-z][a-z0-9-]{1,48}[a-z0-9]", value):
            raise serializers.ValidationError(
                "Use 3–50 lowercase letters, numbers or hyphens; this address must not be reserved."
            )
        matches = BusinessApplication.objects.filter(slug__iexact=value)
        if self.instance:
            matches = matches.exclude(pk=self.instance.pk)
        if matches.exists() or Business.objects.filter(slug=value).exists():
            raise serializers.ValidationError("This store address is already taken.")
        return value

    def validate_country(self, value):
        value = value.upper()
        if value not in {"KE", "UG", "TZ", "RW", "US", "GB", "ZA", "NG", "GH"}:
            raise serializers.ValidationError("Choose a supported launch country.")
        return value

    def validate_currency(self, value):
        value = value.upper()
        if value not in {"KES", "UGX", "TZS", "RWF", "USD", "GBP", "ZAR", "NGN", "GHS"}:
            raise serializers.ValidationError("Choose a supported store currency.")
        return value


class ReviewSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["approved", "changes_requested", "rejected"])
    note = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")

    def validate(self, data):
        if data["decision"] != "approved" and not data["note"].strip():
            raise serializers.ValidationError(
                {"note": "Include a reason so the applicant knows what to do next."}
            )
        return data


class DomainSerializer(serializers.ModelSerializer):
    class Meta:
        model = Domain
        fields = ["hostname", "verified", "is_primary"]


class BusinessSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    domains = DomainSerializer(many=True, read_only=True)
    storefront_url = serializers.SerializerMethodField()

    def get_storefront_url(self, obj) -> str:
        domain = next(
            (domain for domain in obj.domains.all() if domain.verified and domain.is_primary), None
        )
        return (
            settings.STOREFRONT_URL_PATTERN.format(hostname=domain.hostname).rstrip("/")
            if domain
            else ""
        )

    def get_role(self, obj) -> str:
        return obj.memberships.get(user=self.context["request"].user).role

    class Meta:
        model = Business
        fields = [
            "id",
            "name",
            "slug",
            "country",
            "currency",
            "provisioning_status",
            "suspended",
            "published",
            "role",
            "domains",
            "storefront_url",
        ]


class SettingsSerializer(serializers.ModelSerializer):
    description = RichTextField(500, required=False, allow_blank=True)
    return_refund_policy = RichTextField(20000, required=False, allow_blank=True)
    privacy_policy = RichTextField(20000, required=False, allow_blank=True)
    terms_conditions = RichTextField(20000, required=False, allow_blank=True)
    tax_rate = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=0, max_value=100, required=False
    )
    logo_url = serializers.SerializerMethodField()
    cover_url = serializers.SerializerMethodField()
    surface_tone = serializers.ChoiceField(choices=["taupe", "sky", "mauve", "olive", "cream"])
    published = serializers.BooleanField(source="business.published", required=False)
    featured_product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.none(), required=False, allow_null=True
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance:
            self.fields["featured_product"].queryset = Product.objects.filter(
                business_id=self.instance.business_id
            )

    def validate_featured_product(self, product):
        # Preserve an existing choice if it subsequently becomes a draft; the
        # storefront falls back safely until that product is published again.
        if (
            product
            and product.status != "published"
            and product.pk != self.instance.featured_product_id
        ):
            raise serializers.ValidationError(
                "Choose a published product or use the automatic selection."
            )
        return product

    def get_logo_url(self, instance) -> str:
        if not instance.logo:
            return ""
        token = signing.TimestampSigner(salt="mshoppa.store.logo.v1").sign(instance.logo.name)
        return f"/api/store-logos/{instance.business_id}/?token={quote(token, safe='')}"

    def get_cover_url(self, instance) -> str:
        if not instance.cover:
            return ""
        token = signing.TimestampSigner(salt="mshoppa.store.cover.v1").sign(instance.cover.name)
        return f"/api/store-covers/{instance.business_id}/?token={quote(token, safe='')}"

    def validate(self, attrs):
        for field in ["instagram_url", "facebook_url", "tiktok_url", "x_url", "linkedin_url"]:
            value = attrs.get(field, "")
            if value:
                parsed = urlsplit(value)
                if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
                    raise serializers.ValidationError(
                        {field: "Use an http or https link without login credentials."}
                    )
        for field in ["contact_phone", "whatsapp_number"]:
            if attrs.get(field):
                number = re.sub(r"[\s().-]", "", attrs[field])
                pattern = r"\+?[1-9]\d{8,14}" if field == "whatsapp_number" else r"\+?\d{3,15}"
                if not re.fullmatch(pattern, number):
                    raise serializers.ValidationError(
                        {field: "Enter a valid phone number. WhatsApp requires the country code."}
                    )
                attrs[field] = number
        return attrs

    def update(self, instance, validated_data):
        business_data = validated_data.pop("business", {})
        instance = super().update(instance, validated_data)
        if "published" in business_data:
            instance.business.published = business_data["published"]
            instance.business.save(update_fields=["published"])
        return instance

    class Meta:
        model = StoreSettings
        fields = [
            "headline",
            "description",
            "contact_email",
            "tax_rate",
            "stripe_enabled",
            "mpesa_enabled",
            "contact_phone",
            "contact_address",
            "whatsapp_number",
            "logo_url",
            "cover_url",
            "instagram_url",
            "facebook_url",
            "tiktok_url",
            "x_url",
            "linkedin_url",
            "return_refund_policy",
            "privacy_policy",
            "terms_conditions",
            "theme_id",
            "surface_tone",
            "published",
            "featured_product",
        ]
        read_only_fields = ["theme_id"]
