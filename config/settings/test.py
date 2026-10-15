from .base import *  # noqa: F403

DEBUG = False
SECRET_KEY = "tests-only-insecure"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
