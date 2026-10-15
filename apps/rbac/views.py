from django.contrib.auth.models import Group
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.audit import record_audit_event
from apps.users.models import User
from apps.users.permissions import IsActiveSuperuser

from .serializers import (
    PermissionReadSerializer,
    RoleSerializer,
    UserRolesSerializer,
    assignable_permissions,
)


class RoleViewSet(viewsets.ModelViewSet):
    queryset = Group.objects.all().prefetch_related("permissions__content_type").order_by("name")
    serializer_class = RoleSerializer
    permission_classes = (IsActiveSuperuser,)
    http_method_names = ("get", "post", "patch", "delete", "head", "options")

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    def perform_create(self, serializer):
        role = serializer.save()
        record_audit_event(
            actor=self.request.user,
            action="rbac.role.created",
            target_type="auth.Group",
            target_id=role.pk,
            changes={"name": role.name},
        )

    def perform_update(self, serializer):
        instance = serializer.instance
        old_name = instance.name
        old_codes = sorted(
            f"{p.content_type.app_label}.{p.codename}"
            for p in instance.permissions.select_related("content_type")
        )
        role = serializer.save()
        new_codes = sorted(
            f"{p.content_type.app_label}.{p.codename}"
            for p in role.permissions.select_related("content_type")
        )
        changes = {}
        if old_name != role.name:
            changes["name"] = {"before": old_name, "after": role.name}
        if old_codes != new_codes:
            changes["permission_codes"] = {"before": old_codes, "after": new_codes}
        if changes:
            record_audit_event(
                actor=self.request.user,
                action="rbac.role.updated",
                target_type="auth.Group",
                target_id=role.pk,
                changes=changes,
            )

    def perform_destroy(self, instance):
        if instance.user_set.exists():
            raise ValidationError({"detail": _("Cannot delete a role assigned to users.")})
        role_id = instance.pk
        role_name = instance.name
        instance.delete()
        record_audit_event(
            actor=self.request.user,
            action="rbac.role.deleted",
            target_type="auth.Group",
            target_id=role_id,
            changes={"name": role_name},
        )


class PermissionViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = PermissionReadSerializer
    permission_classes = (IsActiveSuperuser,)
    http_method_names = ("get", "head", "options")

    def get_queryset(self):
        return assignable_permissions().order_by("content_type__app_label", "codename")


class UserRolesView(APIView):
    permission_classes = (IsActiveSuperuser,)

    def get(self, request, user_id):
        user = get_object_or_404(User.objects.prefetch_related("groups"), pk=user_id)
        return Response(
            {
                "user_id": str(user.pk),
                "roles": [{"id": role.pk, "name": role.name} for role in user.groups.all()],
            }
        )

    @transaction.atomic
    def put(self, request, user_id):
        # Lock the user so concurrent role replacement requests are serialized.
        user = get_object_or_404(User.objects.select_for_update(), pk=user_id)
        serializer = UserRolesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        before = sorted(user.groups.values_list("pk", flat=True))
        user.groups.set(serializer.validated_data["role_ids"])
        after = sorted(user.groups.values_list("pk", flat=True))
        if before != after:
            record_audit_event(
                actor=request.user,
                action="rbac.user.roles.changed",
                target_type="users.User",
                target_id=user.pk,
                changes={"role_ids": {"before": before, "after": after}},
            )
        return Response(status=status.HTTP_204_NO_CONTENT)
