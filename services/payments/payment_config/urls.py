from django.http import JsonResponse
from django.urls import path

from simulator.checkout_views import CheckoutView
from simulator.configuration import ConfigurationView
from simulator.provider_views import (
    ProvidersView,
    RefreshPaymentView,
    StartPaymentView,
    StripeWebhookView,
    VentyWebhookView,
)
from simulator.views import (
    CsrfView,
    DummyProviderWebhookView,
    SessionCreateView,
    SessionView,
    SimulateView,
)

urlpatterns = [
    path("api/checkout/", CheckoutView.as_view()),
    path("api/configuration/", ConfigurationView.as_view()),
    path("api/providers/", ProvidersView.as_view()),
    path("api/sessions/<str:token>/start/", StartPaymentView.as_view()),
    path("api/sessions/<str:token>/refresh/", RefreshPaymentView.as_view()),
    path("api/webhooks/stripe/", StripeWebhookView.as_view()),
    path("api/webhooks/venty/mpesa/", VentyWebhookView.as_view()),
    path(
        "api/health/",
        lambda request: JsonResponse({"service": "payments", "mode": "local-payments"}),
    ),
    path("api/auth/csrf/", CsrfView.as_view()),
    path("api/sessions/", SessionCreateView.as_view()),
    path("api/sessions/<str:token>/", SessionView.as_view()),
    path("api/sessions/<str:token>/simulate/", SimulateView.as_view()),
    path("api/webhooks/dummy/<str:provider>/", DummyProviderWebhookView.as_view()),
]
