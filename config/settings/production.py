from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured

from . import base
from .base import *  # noqa: F403

DEBUG = False
SECRET_KEY = base.env("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = base.env.list("DJANGO_ALLOWED_HOSTS")
DATABASES = {"default": base.env.db("DATABASE_URL")}

if SECRET_KEY.startswith("unsafe-") or len(SECRET_KEY) < 32:
    raise ImproperlyConfigured("Use a secure, unique DJANGO_SECRET_KEY in production.")
if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured("Set explicit DJANGO_ALLOWED_HOSTS in production.")

SECURE_SSL_REDIRECT = base.env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = base.env.int("DJANGO_HSTS_SECONDS", default=0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

# Never trust spoofable forwarding headers without a controlled reverse proxy.
if base.env.bool("DJANGO_TRUST_PROXY_SSL_HEADER", default=False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Production mail transport may never be the console backend (tokens would leak to logs).
smtp_host = base.env("SMTP_HOST", default="")
if base.AUTH_EMAIL_FLOWS_ENABLED:
    if not smtp_host:
        raise ImproperlyConfigured("SMTP_HOST is required for email account workflows.")
    if base.DEFAULT_FROM_EMAIL.endswith("example.test>"):
        raise ImproperlyConfigured("Configure DEFAULT_FROM_EMAIL for production.")
    for setting_value in (base.AUTH_VERIFICATION_URL, base.AUTH_PASSWORD_RESET_URL):
        address = urlsplit(setting_value)
        if address.scheme != "https" or not address.hostname or address.username:
            raise ImproperlyConfigured("Email action URLs must use an HTTPS origin.")

if smtp_host:
    mail_tls = base.env.bool("SMTP_USE_TLS", default=True)
    mail_ssl = base.env.bool("SMTP_USE_SSL", default=False)
    if mail_tls == mail_ssl:
        raise ImproperlyConfigured("Enable exactly one of SMTP_USE_TLS or SMTP_USE_SSL.")
    MAILERS = {
        "default": {
            "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
            "OPTIONS": {
                "host": smtp_host,
                "port": base.env.int("SMTP_PORT", default=587 if mail_tls else 465),
                "username": base.env("SMTP_USER", default=""),
                "password": base.env("SMTP_PASSWORD", default=""),
                "use_tls": mail_tls,
                "use_ssl": mail_ssl,
                "timeout": 10,
            },
        }
    }
else:
    MAILERS = {"default": {"BACKEND": "django.core.mail.backends.dummy.EmailBackend"}}

# Require explicit opt-in for a single-instance persistent local media volume.
if (
    "apps.storage" in base.INSTALLED_APPS
    and base.STORAGE_BACKEND == "local"
    and not base.env.bool("STORAGE_ALLOW_LOCAL_PRODUCTION", default=False)
):
    raise ImproperlyConfigured(
        "Configure STORAGE_BACKEND=s3, or explicitly enable persistent local storage."
    )
if base.STORAGE_BACKEND == "s3":
    s3_endpoint = base.env("S3_ENDPOINT_URL", default="")
    if s3_endpoint and urlsplit(s3_endpoint).scheme != "https":
        if not base.env.bool("S3_ALLOW_INSECURE_ENDPOINT", default=False):
            raise ImproperlyConfigured("S3 endpoint must use HTTPS in production.")
