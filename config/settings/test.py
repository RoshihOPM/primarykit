from .base import *  # noqa: F403

DEBUG = False
SECRET_KEY = "primarykit-tests-only-not-for-production-8a1fd90697d3e77ad2"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
