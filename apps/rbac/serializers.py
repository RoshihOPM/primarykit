from django.contrib.auth.models import Group, Permission
from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers


def assignable_permissions():
    """Explicit allowlist; never expose every installed Django permission by default."""
    from django.conf import settings

    codes = getattr(settings, "RBAC_ASSIGNABLE_PERMISSIONS", [])
    predicate = Q(pk__in=[])
    for value in codes:
        if not isinstance(value, str) or value.count(".") != 1:
            continue
        app, code = value.split(".")
        predicate |= Q(content_type__app_label=app, codename=code)
    return Permission.objects.filter(predicate).select_related("content_type")


def permission_code(permission):
    return f"{permission.content_type.app_label}.{permission.codename}"


class PermissionReadSerializer(serializers.ModelSerializer):
    code = serializers.SerializerMethodField()

    class Meta:
        model = Permission
        fields = ("id", "code", "name")
        read_only_fields = fields

    def get_code(self, permission):
        return permission_code(permission)


class RoleSerializer(serializers.ModelSerializer):
    permission_codes = serializers.ListField(
        child=serializers.CharField(max_length=150),
        required=False,
        allow_empty=True,
        write_only=True,
    )
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = ("id", "name", "permissions", "permission_codes")
        read_only_fields = ("id", "permissions")

    def get_permissions(self, role):
        return sorted(permission_code(permission) for permission in role.permissions.all())

    def validate_permission_codes(self, codes):
        if len(codes) != len(set(codes)):
            raise serializers.ValidationError(_("Permission codes must be unique."))
        allowed = {permission_code(p): p for p in assignable_permissions()}
        unknown = set(codes).difference(allowed)
        if unknown:
            raise serializers.ValidationError(_("Unknown or non-assignable permission code."))
        return [allowed[code] for code in codes]

    @transaction.atomic
    def create(self, validated_data):
        permissions = validated_data.pop("permission_codes", [])
        group = Group.objects.create(**validated_data)
        group.permissions.set(permissions)
        return group

    @transaction.atomic
    def update(self, instance, validated_data):
        permissions = validated_data.pop("permission_codes", None)
        instance = super().update(instance, validated_data)
        if permissions is not None:
            instance.permissions.set(permissions)
        return instance


class UserRolesSerializer(serializers.Serializer):
    role_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=True,
        required=True,
    )

    def validate_role_ids(self, ids):
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError(_("Role IDs must be unique."))
        roles = list(Group.objects.filter(pk__in=ids))
        if len(roles) != len(ids):
            raise serializers.ValidationError(_("Unknown role ID."))
        return roles
