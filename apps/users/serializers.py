from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError, transaction
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import User


class UserReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "first_name", "last_name", "date_joined")
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
                return User.objects.create_user(**validated_data)
        except IntegrityError as exc:
            raise serializers.ValidationError(
                _("Unable to register with supplied details.")
            ) from exc


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        attrs[self.username_field] = User.objects.normalize_identity(attrs[self.username_field])
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
