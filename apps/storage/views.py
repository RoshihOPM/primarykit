from django.core.files.storage import storages
from django.http import FileResponse, Http404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.organizations.scoping import FULL_ACCESS, organization_scope

from .models import StoredFile
from .serializers import StoredFileReadSerializer, StoredFileUploadSerializer
from .services import InvalidUpload, save_private_file, soft_delete_private_file


class StoredFileViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = (IsAuthenticated,)
    queryset = StoredFile.objects.filter(deleted_at__isnull=True)
    http_method_names = ("get", "post", "delete", "head", "options")

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.get_scope()

    def get_scope(self):
        if not hasattr(self, "_tenant_scope"):
            self._tenant_scope = organization_scope(
                user=self.request.user, org_id=self.kwargs["org_id"]
            )
        return self._tenant_scope

    def get_queryset(self):
        organization, membership = self.get_scope()
        queryset = super().get_queryset().filter(organization=organization)
        if membership.role in FULL_ACCESS:
            return queryset
        return queryset.filter(owner=self.request.user)

    def get_serializer_class(self):
        if self.action == "create":
            return StoredFileUploadSerializer
        return StoredFileReadSerializer

    def create(self, request, *args, **kwargs):
        data = self.get_serializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            file = save_private_file(
                owner=request.user,
                organization=self.get_scope()[0],
                upload=data.validated_data["file"],
            )
        except InvalidUpload as exc:
            raise ValidationError({"file": str(exc)}) from exc
        return Response(StoredFileReadSerializer(file).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="download")
    def download(self, request, pk=None):
        file = self.get_object()
        try:
            stream = storages["default"].open(file.object_key, "rb")
        except (FileNotFoundError, OSError) as exc:
            raise Http404("File not found") from exc
        response = FileResponse(
            stream,
            content_type=file.content_type,
            as_attachment=True,
            filename=file.original_name,
        )
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    def perform_destroy(self, instance):
        soft_delete_private_file(
            file=instance, actor=self.request.user, organization=self.get_scope()[0]
        )
