from django.contrib.auth.models import Group
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

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

    def perform_destroy(self, instance):
        if instance.user_set.exists():
            raise ValidationError({"detail": _("Cannot delete a role assigned to users.")})
        instance.delete()


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
        user.groups.set(serializer.validated_data["role_ids"])
        return Response(status=status.HTTP_204_NO_CONTENT)
