import binascii
import uuid

from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.core.audit import record_audit_event

from .tokens import email_verification_token

User = get_user_model()


def get_token_user(uid):
    """No user identity is returned to unauthenticated callers."""
    try:
        pk = uuid.UUID(force_str(urlsafe_base64_decode(uid)))
    except (ValueError, TypeError, UnicodeDecodeError, OverflowError, binascii.Error):
        return None
    return User.objects.filter(pk=pk).first()


class EmailRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class TokenConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField(max_length=255)
    token = serializers.CharField(max_length=255)

    def validate(self, attrs):
        user = get_token_user(attrs["uid"])
        if user is None:
            raise serializers.ValidationError(_("Invalid or expired confirmation link."))
        attrs["user"] = user
        return attrs


class VerifyEmailSerializer(TokenConfirmSerializer):
    def validate(self, attrs):
        attrs = super().validate(attrs)
        user = attrs["user"]
        if (
            not user.is_active
            or user.email_verified
            or not email_verification_token.check_token(user, attrs["token"])
        ):
            raise serializers.ValidationError(_("Invalid or expired confirmation link."))
        return attrs

    @transaction.atomic
    def save(self):
        user = User.objects.select_for_update().get(pk=self.validated_data["user"].pk)
        if (
            not user.is_active
            or user.email_verified
            or not email_verification_token.check_token(user, self.validated_data["token"])
        ):
            raise serializers.ValidationError(_("Invalid or expired confirmation link."))
        user.email_verified = True
        user.save(update_fields=["email_verified"])
        record_audit_event(
            actor=None, action="users.email.verified", target_type="users.User",
            target_id=user.pk,
        )
        return user


class PasswordResetConfirmSerializer(TokenConfirmSerializer):
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        user = attrs["user"]
        if not user.is_active or not default_token_generator.check_token(user, attrs["token"]):
            raise serializers.ValidationError(_("Invalid or expired confirmation link."))
        password_validation.validate_password(attrs["new_password"], user=user)
        return attrs

    @transaction.atomic
    def save(self):
        user = User.objects.select_for_update().get(pk=self.validated_data["user"].pk)
        if not user.is_active or not default_token_generator.check_token(
            user, self.validated_data["token"]
        ):
            raise serializers.ValidationError(_("Invalid or expired confirmation link."))
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        record_audit_event(
            actor=None, action="users.password.reset", target_type="users.User",
            target_id=user.pk,
        )
        return user
