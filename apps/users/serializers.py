from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.utils import get_md5_hash_password

from apps.core.audit import record_audit_event

from .domain import may_authenticate, may_deactivate
from .email_services import send_verification_email
from .models import DeviceSession, User
from .sessions import create_session, expires_at, locked_session


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
                record_audit_event(
                    actor=None,
                    action="users.registered",
                    target_type="users.User",
                    target_id=user.pk,
                )
                return user
        except IntegrityError as exc:
            raise serializers.ValidationError(
                _("Unable to register with supplied details.")
            ) from exc


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    @transaction.atomic
    def validate(self, attrs):
        attrs[self.username_field] = User.objects.normalize_identity(attrs[self.username_field])
        tokens = super().validate(attrs)
        if not may_authenticate(active=self.user.is_active, verified=self.user.email_verified):
            raise AuthenticationFailed(
                self.error_messages["no_active_account"], code="no_active_account"
            )
        # Serialize session creation against password changes and revoke-all.
        owner = User.objects.select_for_update().get(pk=self.user.pk)
        if (
            not may_authenticate(active=owner.is_active, verified=owner.email_verified)
            or owner.password != self.user.password
        ):
            raise AuthenticationFailed(
                self.error_messages["no_active_account"], code="no_active_account"
            )
        refresh = RefreshToken(tokens["refresh"])
        request = self.context.get("request")
        create_session(
            user=owner,
            refresh=refresh,
            user_agent=request.META.get("HTTP_USER_AGENT", "") if request else "",
        )
        return {"refresh": str(refresh), "access": str(refresh.access_token)}


class PasswordBoundTokenRefreshSerializer(TokenRefreshSerializer):
    """Require an active, account-owned session and one-time refresh rotation."""

    @transaction.atomic
    def validate(self, attrs):
        try:
            refresh = RefreshToken(attrs["refresh"])
            user_id = refresh[api_settings.USER_ID_CLAIM]
            user = User.objects.select_for_update().get(pk=user_id, is_active=True)
        except (TokenError, KeyError, ValueError, User.DoesNotExist) as exc:
            raise InvalidToken(_("Token is invalid or expired.")) from exc

        if not may_authenticate(active=user.is_active, verified=user.email_verified):
            raise InvalidToken(_("Token is invalid or expired."))

        if api_settings.CHECK_REVOKE_TOKEN and refresh.get(
            api_settings.REVOKE_TOKEN_CLAIM
        ) != get_md5_hash_password(user.password):
            raise InvalidToken(_("Token is invalid or expired."))

        session = locked_session(user=user, refresh=refresh)
        # Re-evaluate the blacklist *under* the session lock to prevent concurrent
        # refresh requests from both consuming the same token.
        try:
            RefreshToken(attrs["refresh"])
        except TokenError as exc:
            raise InvalidToken(_("Token is invalid or expired.")) from exc
        tokens = super().validate(attrs)
        session.last_seen_at = timezone.now()
        if "refresh" in tokens:
            session.expires_at = expires_at(RefreshToken(tokens["refresh"]))
        session.save(update_fields=["last_seen_at", "expires_at"])
        return tokens


class DeviceSessionReadSerializer(serializers.ModelSerializer):
    is_current = serializers.SerializerMethodField()

    class Meta:
        model = DeviceSession
        fields = (
            "id", "browser", "os", "device_type", "created_at",
            "last_seen_at", "expires_at", "is_current",
        )
        read_only_fields = fields

    def get_is_current(self, session):
        token = getattr(self.context["request"], "auth", None)
        return bool(token and str(token.get("sid", "")) == str(session.pk))


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        user = self.context.get("user") or self.context["request"].user
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
        if (
            self.instance
            and not value
            and not may_deactivate(
                actor_id=self.context["request"].user.pk, target_id=self.instance.pk
            )
        ):
            raise serializers.ValidationError(_("You cannot deactivate yourself."))
        return value
