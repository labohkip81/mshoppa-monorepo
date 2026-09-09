import os

from config.settings import *  # noqa: F403
from config.settings import DEBUG, LOCAL_DIR, LOCAL_DUMMY_PAYMENTS, REST_FRAMEWORK
from django.core.exceptions import ImproperlyConfigured

if not DEBUG or not LOCAL_DUMMY_PAYMENTS:
    raise ImproperlyConfigured("This payment simulator runs only in local debug/test mode.")
INSTALLED_APPS = ["simulator", "rest_framework"]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "config.middleware.PrivateApiHeaders",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(LOCAL_DIR / "payments.sqlite3"),
        "OPTIONS": {"timeout": 20, "transaction_mode": "IMMEDIATE"},
    }
}
ROOT_URLCONF = "payment_config.urls"
WSGI_APPLICATION = "payment_config.wsgi.application"
AUTH_USER_MODEL = "auth.User"
CSRF_COOKIE_NAME = "mshoppa_payments_csrf"
CSRF_TRUSTED_ORIGINS = ["http://payments.localhost:4204", "http://localhost:4204"]
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "UNAUTHENTICATED_USER": None,
}

# Provider selection is independent for M-Pesa and cards. Existing sessions retain their backend.
STRIPE_PAYMENT_BACKEND = os.getenv("STRIPE_PAYMENT_BACKEND", "stripe")
MPESA_PAYMENT_BACKEND = os.getenv("MPESA_PAYMENT_BACKEND", "venty")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
VENTY_MPESA_BASE_URL = os.getenv("VENTY_MPESA_BASE_URL", "https://mpesa.venti.africa/mpesa/api/v1")
VENTY_MPESA_ENABLED = os.getenv("VENTY_MPESA_ENABLED", "0") == "1"
VENTY_MPESA_TENANT_ID = os.getenv("VENTY_MPESA_TENANT_ID", "")
VENTY_MPESA_USE_DEFAULT_CONFIG = os.getenv("VENTY_MPESA_USE_DEFAULT_CONFIG", "0") == "1"
VENTY_MPESA_API_TOKEN = os.getenv("VENTY_MPESA_API_TOKEN", "")
VENTY_MPESA_CALLBACK_URL = os.getenv("VENTY_MPESA_CALLBACK_URL", "")
VENTY_MPESA_CALLBACK_SECRET = os.getenv("VENTY_MPESA_CALLBACK_SECRET", "")
if STRIPE_PAYMENT_BACKEND not in {"stripe", "simulator"} or MPESA_PAYMENT_BACKEND not in {
    "venty",
    "simulator",
}:
    raise ImproperlyConfigured("Choose stripe/simulator and venty/simulator payment backends.")

CORE_CHECKOUT_URL = "http://127.0.0.1:8000/api/payments/checkout/"
