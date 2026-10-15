from django.conf import settings
from django.middleware.locale import LocaleMiddleware


def test_supported_languages():
    assert {code for code, _ in settings.LANGUAGES} == {"en", "ru", "ko"}


def test_locale_middleware_is_enabled():
    assert "django.middleware.locale.LocaleMiddleware" in settings.MIDDLEWARE
    assert LocaleMiddleware is not None
