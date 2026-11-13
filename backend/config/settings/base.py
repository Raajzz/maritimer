"""Base settings shared by every environment. Environment-specific files override."""
import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env(name, default=None):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-insecure-secret-key-change-me")
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    "apps.core",
    "apps.accounts",
    "apps.masterdata",
    "apps.vessels",
    "apps.requests",
    "apps.portcalls",
    "apps.disbursements",
    "apps.invoices",
    "apps.payments",
    "apps.disputes",
    "apps.documents",
    "apps.chat",
    "apps.ratings",
    "apps.dashboards",
    "apps.adminpanel",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.RequestContextMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
            ],
        },
    },
]

DATABASES = {
    "default": dj_database_url.parse(
        env("DATABASE_URL", "postgres://maritimer:maritimer@localhost:5432/maritimer"),
        conn_max_age=int(env("DB_CONN_MAX_AGE", "60")),
    )
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(env("MEDIA_ROOT", str(BASE_DIR / "media")))

# ---- Storage --------------------------------------------------------------
# STORAGE_BACKEND=local (dev) or s3 (prod; Cloudflare R2 or any S3-compatible service)
STORAGE_BACKEND = env("STORAGE_BACKEND", "local")
if STORAGE_BACKEND == "s3":
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "bucket_name": env("S3_BUCKET_NAME"),
                "endpoint_url": env("S3_ENDPOINT_URL"),
                "access_key": env("S3_ACCESS_KEY_ID"),
                "secret_key": env("S3_SECRET_ACCESS_KEY"),
                "region_name": env("S3_REGION_NAME", "auto"),
                "signature_version": "s3v4",
                "default_acl": None,
                "querystring_auth": True,
                "querystring_expire": int(env("S3_URL_EXPIRE_SECONDS", "300")),
                "file_overwrite": False,
                "addressing_style": "virtual" if env_bool("S3_VIRTUAL_ADDRESSING", False) else "path",
            },
        },
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    }
    STORAGE_BUCKET_LABEL = env("S3_BUCKET_NAME", "")
else:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    STORAGE_BUCKET_LABEL = "local"

FILE_UPLOAD_MAX_BYTES = int(env("FILE_UPLOAD_MAX_BYTES", str(15 * 1024 * 1024)))
DATA_UPLOAD_MAX_MEMORY_SIZE = FILE_UPLOAD_MAX_BYTES + 1024 * 1024
FILE_ALLOWED_CONTENT_TYPES = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}
FILE_DOWNLOAD_TOKEN_MAX_AGE = int(env("FILE_DOWNLOAD_TOKEN_MAX_AGE", "300"))

# ---- Auth -----------------------------------------------------------------
FIREBASE_PROJECT_ID = env("FIREBASE_PROJECT_ID", "")
FIREBASE_SERVICE_ACCOUNT_JSON_BASE64 = env("FIREBASE_SERVICE_ACCOUNT_JSON_BASE64", "")
FIREBASE_CHECK_REVOKED = env_bool("FIREBASE_CHECK_REVOKED", False)
# Dev-only: accept "Bearer dev:<email>" tokens. Forced off in prod settings.
AUTH_DEV_TOKENS = env_bool("AUTH_DEV_TOKENS", False)

# ---- Domain settings ------------------------------------------------------
FDA_DISPUTE_WINDOW_DAYS = int(env("FDA_DISPUTE_WINDOW_DAYS", "0"))
SETTLEMENT_WRITEOFF_TOLERANCE = env("SETTLEMENT_WRITEOFF_TOLERANCE", "0.00")
DEFAULT_SETTLEMENT_CURRENCY = "USD"

# ---- DRF ------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.core.authentication.FirebaseAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
        "apps.core.permissions.IsApproved",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FormParser",
    ],
    "EXCEPTION_HANDLER": "apps.core.exceptions.exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "COERCE_DECIMAL_TO_STRING": True,
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.UserRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "user": env("THROTTLE_USER", "600/min"),
        "chat": env("THROTTLE_CHAT", "30/min"),
        "upload": env("THROTTLE_UPLOAD", "20/min"),
    },
    "UNAUTHENTICATED_USER": None,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Maritimer API",
    "DESCRIPTION": "Port-call management: requests, PDA/FDA, invoices, payments, disputes, chat.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

# ---- CORS -----------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
CORS_ALLOWED_ORIGIN_REGEXES = env_list("CORS_ALLOWED_ORIGIN_REGEXES", "")
CORS_ALLOW_CREDENTIALS = False
CORS_EXPOSE_HEADERS = ["Content-Disposition"]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
    "loggers": {
        "weasyprint": {"level": "WARNING"},
        "fontTools": {"level": "WARNING"},
    },
}

# drf_spectacular.W001/W002: views are plain APIViews documented in API.md (see PROGRESS.md F2).
# security.W003: CSRF middleware is intentionally absent — auth is a Bearer token, no cookies/sessions.
SILENCED_SYSTEM_CHECKS = ["drf_spectacular.W001", "drf_spectacular.W002", "security.W003"]
