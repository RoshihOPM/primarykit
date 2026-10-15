from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError, transaction
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.utils import get_md5_hash_password

from .email_services import send_verification_email
from .models import User


class UserReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "email_verified", "first_name", "last_name", "date_joined")
        read_only_fields = fields


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("first_name", "last_name")


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)

    def validate(self, attrs):
        attrs["email"] = User.objects.normalize_identity(attrs["email"])
        candidate = User(email=attrs["email"], first_name=attrs.get("first_name", ""))
        validate_password(attrs["password"], user=candidate)
        # Generic validation response rather than exposing duplicate accounts.
        if User.objects.filter(email=attrs["email"]).exists():
            raise serializers.ValidationError(_("Unable to register with supplied details."))
        return attrs

    def create(self, validated_data):
        try:
            with transaction.atomic():
                user = User.objects.create_user(email_verified=False, **validated_data)
                send_verification_email(user)
                return user
        except IntegrityError as exc:
            raise serializers.ValidationError(
                _("Unable to register with supplied details.")
            ) from exc


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        attrs[self.username_field] = User.objects.normalize_identity(attrs[self.username_field])
        tokens = super().validate(attrs)
        if not self.user.email_verified:
            raise AuthenticationFailed(
                self.error_messages["no_active_account"], code="no_active_account"
            )
        return tokens


class PasswordBoundTokenRefreshSerializer(TokenRefreshSerializer):
    """SimpleJWT 5.5.1 does not compare password revocation during refresh."""

    def validate(self, attrs):
        try:
            refresh = RefreshToken(attrs["refresh"])
            user_id = refresh[api_settings.USER_ID_CLAIM]
            user = User.objects.get(pk=user_id, is_active=True)
        except (TokenError, KeyError, ValueError, User.DoesNotExist) as exc:
            raise InvalidToken(_("Token is invalid or expired.")) from exc

        if not user.email_verified:
            raise InvalidToken(_("Token is invalid or expired."))

        if api_settings.CHECK_REVOKE_TOKEN and refresh.get(
            api_settings.REVOKE_TOKEN_CLAIM
        ) != get_md5_hash_password(user.password):
            raise InvalidToken(_("Token is invalid or expired."))

        return super().validate(attrs)


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        user = self.context["request"].user
        if not user.check_password(attrs["current_password"]):
            raise serializers.ValidationError({"current_password": _("Invalid current password.")})
        validate_password(attrs["new_password"], user=user)
        if attrs["current_password"] == attrs["new_password"]:
            raise serializers.ValidationError({"new_password": _("Choose a different password.")})
        return attrs


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(write_only=True)


class AdminUserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "is_active")

    def validate_is_active(self, value):
        if self.instance and self.instance.pk == self.context["request"].user.pk and not value:
            raise serializers.ValidationError(_("You cannot deactivate yourself."))
        return value
