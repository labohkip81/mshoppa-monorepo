import os
from pathlib import Path

from cryptography.fernet import Fernet
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BASE_DIR.parent.parent
LOCAL_DIR = ROOT_DIR / ".local"
DEBUG = os.getenv("DJANGO_DEBUG", "1") == "1"


def secret(name, filename, factory):
    value = os.getenv(name)
    if value:
        return value
    if not DEBUG:
        raise ImproperlyConfigured(f"{name} must be configured in production")
    LOCAL_DIR.mkdir(exist_ok=True, mode=0o700)
    path = LOCAL_DIR / filename
    try:
        with path.open("x") as file:
            file.write(factory())
        path.chmod(0o600)
    except FileExistsError:
        pass
    return path.read_text().strip()


SECRET_KEY = secret(
    "DJANGO_SECRET_KEY", "django-secret", lambda: __import__("secrets").token_urlsafe(64)
)
ENCRYPTION_KEY = secret(
    "MSHOPPA_ENCRYPTION_KEY", "encryption-key", lambda: Fernet.generate_key().decode()
)
BASE_DOMAIN = os.getenv("BASE_DOMAIN", "localhost")
ALLOWED_HOSTS = os.getenv(
    "DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,.localhost,testserver"
).split(",")
MERCHANT_URL = os.getenv("MERCHANT_URL", "http://admin.localhost:4201")
PLATFORM_URL = os.getenv("PLATFORM_URL", "http://platform.localhost:4202")
STOREFRONT_URL = os.getenv("STOREFRONT_URL", "http://localhost:4203")
STOREFRONT_URL_PATTERN = os.getenv("STOREFRONT_URL_PATTERN", "http://{hostname}:4203")
LOCAL_DUMMY_PAYMENTS = DEBUG and os.getenv("LOCAL_DUMMY_PAYMENTS", "1") == "1"
PAYMENT_SIGNING_SECRET = secret(
    "PAYMENT_SIGNING_SECRET", "payment-signing-key", lambda: __import__("secrets").token_urlsafe(48)
)
PAYMENT_SERVICE_URL = "http://127.0.0.1:8001"
PAYMENT_PUBLIC_URL = "http://localhost:4204"
CORE_PAYMENT_CALLBACK_URL = "http://127.0.0.1:8000/api/payments/webhooks/dummy/"
CSRF_TRUSTED_ORIGINS = os.getenv(
    "CSRF_TRUSTED_ORIGINS",
    ",".join(
        [
            MERCHANT_URL,
            PLATFORM_URL,
            "http://localhost:4200",
            "http://localhost:4201",
            "http://localhost:4202",
        ]
    ),
).split(",")
INSTALLED_APPS = [
    "apps.businesses",
    "apps.accounts",
    "apps.catalog",
    "apps.checkout",
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "rest_framework",
    "drf_spectacular",
]
AUTH_USER_MODEL = "accounts.User"
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "config.middleware.PrivateApiHeaders",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.getenv("SQLITE_PATH", str(LOCAL_DIR / "mshoppa.sqlite3")),
        "OPTIONS": {"timeout": 20, "transaction_mode": "IMMEDIATE"},
    }
}
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
MEDIA_ROOT = LOCAL_DIR / "media"
# Uploads spill to temporary files instead of consuming unbounded request memory.
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FILES = 1
USE_TZ = True
TIME_ZONE = "UTC"
LANGUAGE_CODE = "en"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
SESSION_COOKIE_NAME = "mshoppa_session"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_DOMAIN = None
SESSION_COOKIE_AGE = 12 * 60 * 60
CSRF_COOKIE_NAME = "mshoppa_csrf"
CSRF_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
X_FRAME_OPTIONS = "DENY"
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.filebased.EmailBackend")
EMAIL_FILE_PATH = LOCAL_DIR / "mail"
EMAIL_HOST = os.getenv("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "1025"))
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "MSHOPPA <hello@mshoppa.localhost>")
CELERY_BROKER_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:63799/0")
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {"anon": "600/hour" if DEBUG else "120/hour", "user": "1200/hour", "auth": "20/hour"},
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 30,
}
SPECTACULAR_SETTINGS = {"TITLE": "MSHOPPA API", "VERSION": "0.1.0", "COMPONENT_SPLIT_REQUEST": True}
