from django.core.files.storage import storages
from django.http import FileResponse, Http404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

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

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if user.is_superuser and user.is_active:
            return queryset
        return queryset.filter(owner=user)

    def get_serializer_class(self):
        if self.action == "create":
            return StoredFileUploadSerializer
        return StoredFileReadSerializer

    def create(self, request, *args, **kwargs):
        data = self.get_serializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            file = save_private_file(owner=request.user, upload=data.validated_data["file"])
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
        soft_delete_private_file(file=instance, actor=self.request.user)
