import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from apps.feature_flags.services import is_enabled


def test_unknown_flags_are_disabled_by_default():
    assert is_enabled("beta_checkout") is False


@override_settings(FEATURE_FLAGS={"beta_checkout": True, "new_ui": False})
def test_client_controls_flags_explicitly():
    assert is_enabled("beta_checkout") is True
    assert is_enabled("new_ui") is False
    assert is_enabled("missing") is False


@pytest.mark.parametrize("name", ["", "BadName", "private.path", "a" * 65, None])
def test_invalid_flag_names_are_rejected(name):
    with pytest.raises(ValueError):
        is_enabled(name)


@pytest.mark.parametrize("flags", [None, [], {"checkout": 1}, {"BadName": True}])
def test_invalid_configuration_is_rejected(flags):
    with override_settings(FEATURE_FLAGS=flags):
        with pytest.raises(ImproperlyConfigured):
            is_enabled("checkout")
