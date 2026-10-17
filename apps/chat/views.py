from django.core.files.storage import storages
from django.http import FileResponse, Http404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from .serializers import (
    DialogueCreateSerializer,
    DialogueReadSerializer,
    MessageCreateSerializer,
    MessageReadSerializer,
    ReadReceiptSerializer,
)
from .services import (
    create_dialogue,
    get_message_attachment,
    mark_read,
    send_message,
    visible_dialogues,
    visible_messages,
)


class DialogueViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = (IsAuthenticated,)
    throttle_classes = (ScopedRateThrottle,)
    serializer_class = DialogueReadSerializer
    http_method_names = ("get", "post", "head", "options")

    def get_throttles(self):
        self.throttle_scope = "chat_write" if self.request.method == "POST" else "chat_read"
        return super().get_throttles()

    def get_queryset(self):
        return visible_dialogues(self.request.user).order_by("-updated_at", "-id")

    def create(self, request, *args, **kwargs):
        incoming = DialogueCreateSerializer(data=request.data)
        incoming.is_valid(raise_exception=True)
        dialogue = create_dialogue(actor=request.user, **incoming.validated_data)
        return Response(DialogueReadSerializer(dialogue).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=("get", "post"), url_path="messages")
    def messages(self, request, pk=None):
        dialogue = self.get_object()
        if request.method == "POST":
            incoming = MessageCreateSerializer(data=request.data)
            incoming.is_valid(raise_exception=True)
            message = send_message(
                actor=request.user, dialogue_id=dialogue.pk, **incoming.validated_data
            )
            return Response(MessageReadSerializer(message).data, status=status.HTTP_201_CREATED)
        try:
            after = int(request.query_params.get("after", "0"))
            limit = int(request.query_params.get("limit", "50"))
        except (TypeError, ValueError) as exc:
            raise ValidationError("Invalid pagination cursor.") from exc
        if after < 0 or not 1 <= limit <= 50:
            raise ValidationError("Cursor must be nonnegative and limit must be 1 to 50.")
        _, messages = visible_messages(
            actor=request.user, dialogue_id=dialogue.pk, after=after, limit=limit
        )
        return Response(
            {
                "results": MessageReadSerializer(messages, many=True).data,
                "next_after": messages[-1].sequence if messages else after,
            }
        )

    @action(detail=True, methods=("post",), url_path="read")
    def read(self, request, pk=None):
        dialogue = self.get_object()
        incoming = ReadReceiptSerializer(data=request.data)
        incoming.is_valid(raise_exception=True)
        sequence = mark_read(
            actor=request.user,
            dialogue_id=dialogue.pk,
            sequence=incoming.validated_data["sequence"],
        )
        return Response({"read_sequence": sequence})

    @action(
        detail=True,
        methods=("get",),
        url_path=r"messages/(?P<message_id>[^/.]+)/attachment",
    )
    def attachment(self, request, pk=None, message_id=None):
        dialogue = self.get_object()
        attached = get_message_attachment(
            actor=request.user, dialogue_id=dialogue.pk, message_id=message_id
        )
        try:
            stream = storages["default"].open(attached.object_key, "rb")
        except (FileNotFoundError, OSError) as exc:
            raise Http404("Attachment not found.") from exc
        response = FileResponse(
            stream,
            content_type=attached.content_type,
            as_attachment=True,
            filename=attached.original_name,
        )
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response
