from datetime import timedelta
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

from apps.core.module_registry import installed_module_apps

BASE_DIR = Path(__file__).resolve().parents[2]

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="unsafe-local-only")
DEBUG = False
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])
CORS_ALLOWED_ORIGINS = env.list("DJANGO_CORS_ALLOWED_ORIGINS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    *installed_module_apps(),
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# Request correlation middleware is copied only with the optional module.
if "apps.observability" in INSTALLED_APPS:
    MIDDLEWARE.insert(0, "apps.observability.middleware.request_id_middleware")

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgresql://primarykit:primarykit_dev@127.0.0.1:5432/primarykit",
    )
}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=0)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

CATALOG_MODE = "tenant"  # Choose before initial migration; do not change on existing DBs.
INVENTORY_MODE = "tenant"  # Generated standalone projects pin an independent schema.

AUTH_USER_MODEL = "users.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English"), ("ru", "Russian"), ("ko", "Korean")]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = env("DJANGO_TIME_ZONE", default="UTC")
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

MEDIA_ROOT = BASE_DIR / "media"
STORAGE_MAX_FILE_BYTES = env.int("STORAGE_MAX_FILE_BYTES", default=10 * 1024 * 1024)
STORAGE_ALLOWED_MIME_TYPES = ("image/jpeg", "image/png", "image/webp", "application/pdf")
STORAGE_BACKEND = env("STORAGE_BACKEND", default="local")
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {"location": str(MEDIA_ROOT), "base_url": None},
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}
if STORAGE_BACKEND == "s3":
    bucket = env("S3_BUCKET", default="")
    if not bucket:
        raise ImproperlyConfigured("S3_BUCKET is required for S3 storage.")
    options = {
        "bucket_name": bucket,
        "region_name": env("S3_REGION", default="us-east-1"),
        "endpoint_url": env("S3_ENDPOINT_URL", default=None),
        "addressing_style": env("S3_ADDRESSING_STYLE", default="path"),
        "querystring_auth": True,
        "default_acl": None,
        "file_overwrite": False,
    }
    if env("S3_ACCESS_KEY_ID", default=""):
        options["access_key"] = env("S3_ACCESS_KEY_ID")
        options["secret_key"] = env("S3_SECRET_ACCESS_KEY")
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": options,
    }
elif STORAGE_BACKEND != "local":
    raise ImproperlyConfigured("STORAGE_BACKEND must be local or s3.")


REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.users.authentication.VerifiedJWTAuthentication",
        "apps.users.authentication.VerifiedSessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.DefaultPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
}
ALLOW_PUBLIC_REGISTRATION = env.bool("ALLOW_PUBLIC_REGISTRATION", default=False)
AUTH_EMAIL_FLOWS_ENABLED = env.bool("AUTH_EMAIL_FLOWS_ENABLED", default=False)
AUTH_REQUIRE_EMAIL_VERIFICATION = True
AUTH_VERIFICATION_URL = env("AUTH_VERIFICATION_URL", default="http://localhost:3000/verify-email")
AUTH_PASSWORD_RESET_URL = env(
    "AUTH_PASSWORD_RESET_URL", default="http://localhost:3000/reset-password"
)
PASSWORD_RESET_TIMEOUT = env.int("PASSWORD_RESET_TIMEOUT", default=3600)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="PrimaryKit <no-reply@example.test>")
MAILERS = {"default": {"BACKEND": "django.core.mail.backends.console.EmailBackend"}}

# Both optional modules leave the baseline independent of Redis and brokers.
if "apps.chat" in INSTALLED_APPS:
    CHAT_RETENTION_DAYS = env.int("CHAT_RETENTION_DAYS", default=30)
if "apps.realtime" in INSTALLED_APPS:
    REALTIME_ENABLED = env.bool("REALTIME_ENABLED", default=False)
    REALTIME_ALLOWED_ORIGINS = tuple(env.list("REALTIME_ALLOWED_ORIGINS", default=[]))

# Register only trusted application callables; tasks are internal, never user-invoked by name.
# Optional copied Redis cache module. With no explicit opt-in, Django uses local memory.
if "apps.cache" in INSTALLED_APPS:
    from apps.cache.config import build_cache_config

    REDIS_CACHE_ENABLED = env.bool("REDIS_CACHE_ENABLED", default=False)
    REDIS_CACHE_URL = env("REDIS_CACHE_URL", default="")
    REDIS_CACHE_KEY_PREFIX = env("REDIS_CACHE_KEY_PREFIX", default="")
    REDIS_CACHE_TIMEOUT = env.int("REDIS_CACHE_TIMEOUT", default=300)
    # Optional bridge for third-party Django extensions. Native CacheService is
    # independent of Django's CACHES registry.
    REDIS_CACHE_DJANGO_BACKEND = env("REDIS_CACHE_DJANGO_BACKEND", default="none")
    if REDIS_CACHE_DJANGO_BACKEND != "none":
        CACHES = {
            "default": build_cache_config(
                enabled=REDIS_CACHE_ENABLED,
                url=REDIS_CACHE_URL,
                prefix=REDIS_CACHE_KEY_PREFIX,
                timeout=REDIS_CACHE_TIMEOUT,
                backend=REDIS_CACHE_DJANGO_BACKEND,
            )
        }

# Redis shared auth limits are optional and enabled explicitly in deployed clients.
if "apps.rate_limit" in INSTALLED_APPS:
    SHARED_ACCOUNT_THROTTLE_ENABLED = env.bool("SHARED_ACCOUNT_THROTTLE_ENABLED", default=False)

# Optional Celery adapter. No broker is connected during Django initialization.
if "apps.celery_tasks" in INSTALLED_APPS:
    CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="")
    CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=None) or None
    CELERY_TASK_SERIALIZER = "json"
    CELERY_RESULT_SERIALIZER = "json"
    CELERY_ACCEPT_CONTENT = ["json"]  # Reject pickle and other unsafe serializers.
    CELERY_TASK_IGNORE_RESULT = True
    CELERY_TASK_ACKS_LATE = True
    CELERY_TASK_REJECT_ON_WORKER_LOST = True
    CELERY_WORKER_PREFETCH_MULTIPLIER = 1
    CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
    CELERY_TASK_SOFT_TIME_LIMIT = 240
    CELERY_TASK_TIME_LIMIT = 300
    CELERY_RESULT_EXPIRES = 3600

BACKGROUND_JOB_HANDLERS = {}  # e.g. {"mail.send": "apps.myapp.jobs.send_email"}
# Client-owned event handlers; Outbox reuses Tasks rows and requires a worker.
OUTBOX_EVENT_HANDLERS = {}  # e.g. {"lead.created": "apps.leads.events.publish_created"}
if "apps.outbox" in INSTALLED_APPS:
    BACKGROUND_JOB_HANDLERS["outbox.dispatch"] = "apps.outbox.services.dispatch"

# Privacy is opt-in: no policy or automatic execution exists by default.
if "apps.privacy" in INSTALLED_APPS:
    PRIVACY_RETENTION_POLICIES = {}
    PRIVACY_AUTO_EXECUTION_ENABLED = False
    BACKGROUND_JOB_HANDLERS["privacy.execute"] = "apps.privacy.services.process_retention_job"

RBAC_ASSIGNABLE_PERMISSIONS = []  # Populate in the generated project.
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {
    "account_login": "5/min",
    "account_registration": "3/hour",
    "account_refresh": "30/min",
    "account_password": "5/hour",
    "account_email_request": "3/hour",
    "account_email_confirm": "10/min",
}
if "apps.chat" in INSTALLED_APPS:
    REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"].update(
        {"chat_read": "120/min", "chat_write": "30/min"}
    )


SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "CHECK_REVOKE_TOKEN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "PrimaryKit API",
    "DESCRIPTION": "Reusable Django API backend",
    "VERSION": "0.1.0",
}
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s %(levelname)s %(name)s: %(message)s",
        }
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "default"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
}

if "apps.observability" in INSTALLED_APPS:
    LOGGING["formatters"]["json"] = {"()": "apps.observability.logging.JsonLogFormatter"}
    LOGGING["handlers"]["console"]["formatter"] = "json"
