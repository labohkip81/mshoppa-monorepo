from django.db import connection
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView
from rest_framework.routers import DefaultRouter

from apps.accounts.views import (
    CsrfView,
    LoginView,
    LogoutView,
    MeView,
    MfaSetupView,
    MfaVerifyView,
    RegisterView,
    VerifyEmailView,
)
from apps.businesses.logos import (
    StoreCoverContentView,
    StoreCoverView,
    StoreLogoContentView,
    StoreLogoView,
)
from apps.businesses.management_api import (
    MerchantCustomerViewSet,
    MerchantDomainViewSet,
    MerchantOrderViewSet,
    MerchantPaymentViewSet,
    MerchantPromotionViewSet,
    MerchantStaffViewSet,
)
from apps.businesses.payment_settings import PaymentSettingsView
from apps.businesses.storefront import (
    PublicStoreView,
    SignedStorePreviewView,
    StorePreviewLinkView,
    StorePreviewView,
)
from apps.businesses.views import (
    ApplicationViewSet,
    BusinessSettingsView,
    BusinessViewSet,
    PlatformApplicationViewSet,
)
from apps.businesses.wallet import (
    CancelWithdrawalView,
    PlatformWalletView,
    PlatformWithdrawalReviewView,
    WalletView,
)
from apps.catalog.images import ProductImageContentView
from apps.catalog.views import ProductViewSet
from apps.checkout.handoff import CheckoutHandoffView, PaymentCheckoutView
from apps.checkout.views import CartQuoteView, CheckoutView, DummyWebhookView, OrderStatusView

router = DefaultRouter()
router.register("applications", ApplicationViewSet, basename="application")
router.register(
    "platform/applications", PlatformApplicationViewSet, basename="platform-application"
)
router.register("businesses", BusinessViewSet, basename="business")
for resource, view in [
    ("orders", MerchantOrderViewSet),
    ("payments", MerchantPaymentViewSet),
    ("customers", MerchantCustomerViewSet),
    ("domains", MerchantDomainViewSet),
    ("staff", MerchantStaffViewSet),
    ("promotions", MerchantPromotionViewSet),
]:
    router.register(
        r"businesses/(?P<business_id>[0-9a-f-]+)/" + resource, view, basename="merchant-" + resource
    )
router.register(
    r"businesses/(?P<business_id>[0-9a-f-]+)/products", ProductViewSet, basename="product"
)


def health(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return JsonResponse({"status": "ok", "service": "core"})


urlpatterns = [
    path('api/businesses/<uuid:business_id>/payments/wallet/', WalletView.as_view()),
    path('api/businesses/<uuid:business_id>/payments/withdrawals/<uuid:withdrawal_id>/cancel/', CancelWithdrawalView.as_view()),
    path('api/platform/wallet/', PlatformWalletView.as_view()),
    path('api/platform/withdrawals/<uuid:withdrawal_id>/review/', PlatformWithdrawalReviewView.as_view()),
    path('api/businesses/<uuid:business_id>/payments/configuration/', PaymentSettingsView.as_view()),
    path("api/cart/quote/", CartQuoteView.as_view()),
    path("api/checkout/handoff/", CheckoutHandoffView.as_view()),
    path("api/payments/checkout/", PaymentCheckoutView.as_view()),
    path("api/checkout/", CheckoutView.as_view()),
    path("api/orders/<str:token>/", OrderStatusView.as_view()),
    path("api/payments/webhooks/dummy/", DummyWebhookView.as_view()),
    path("api/businesses/<uuid:business_id>/logo/", StoreLogoView.as_view()),
    path("api/store-logos/<uuid:business_id>/", StoreLogoContentView.as_view()),
    path("api/businesses/<uuid:business_id>/cover/", StoreCoverView.as_view()),
    path("api/store-covers/<uuid:business_id>/", StoreCoverContentView.as_view()),
    path("api/health/", health),
    path("api/product-images/<uuid:image_id>/content/", ProductImageContentView.as_view()),
    path("api/storefront/", PublicStoreView.as_view()),
    path("api/storefront/preview/", SignedStorePreviewView.as_view()),
    path("api/businesses/<uuid:business_id>/preview-link/", StorePreviewLinkView.as_view()),
    path("api/businesses/<uuid:business_id>/preview/", StorePreviewView.as_view()),
    path("api/schema/", SpectacularAPIView.as_view()),
    path("api/auth/csrf/", CsrfView.as_view()),
    path("api/auth/register/", RegisterView.as_view()),
    path("api/auth/verify-email/", VerifyEmailView.as_view()),
    path("api/auth/login/", LoginView.as_view()),
    path("api/auth/mfa/setup/", MfaSetupView.as_view()),
    path("api/auth/mfa/verify/", MfaVerifyView.as_view()),
    path("api/auth/me/", MeView.as_view()),
    path("api/auth/logout/", LogoutView.as_view()),
    path("api/businesses/<uuid:business_id>/settings/", BusinessSettingsView.as_view()),
    path("api/", include(router.urls)),
]
