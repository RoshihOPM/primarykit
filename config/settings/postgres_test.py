"""Run pytest against the real PostgreSQL service (never production data)."""

from .base import *  # noqa: F403

DEBUG = False
SECRET_KEY = "tests-only-insecure"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
