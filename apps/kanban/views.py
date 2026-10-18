"""Authenticated owner-only Kanban API; no implicit team access."""

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Board, Card, Column
from .serializers import BoardSerializer, CardSerializer, ColumnSerializer, MoveSerializer
from .services import move_card


class BoardViewSet(viewsets.ModelViewSet):
    permission_classes = (IsAuthenticated,)
    serializer_class = BoardSerializer
    http_method_names = ("get", "post", "patch", "head", "options")

    def get_queryset(self):
        return Board.objects.filter(owner=self.request.user).order_by("-created_at")

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class ColumnViewSet(viewsets.ModelViewSet):
    permission_classes = (IsAuthenticated,)
    serializer_class = ColumnSerializer
    http_method_names = ("get", "post", "patch", "head", "options")

    def get_queryset(self):
        return Column.objects.filter(board__owner=self.request.user).order_by(
            "board", "position", "pk"
        )

    def perform_create(self, serializer):
        board = get_object_or_404(
            Board, pk=serializer.validated_data["board"].pk, owner=self.request.user
        )
        serializer.save(board=board)

    def perform_update(self, serializer):
        if "board" in serializer.validated_data:
            raise ValidationError({"board": "Board cannot be changed."})
        serializer.save()


class CardViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = (IsAuthenticated,)
    serializer_class = CardSerializer
    http_method_names = ("get", "post", "patch", "head", "options")

    def get_queryset(self):
        return Card.objects.filter(board__owner=self.request.user).order_by(
            "column", "position", "pk"
        )

    def perform_create(self, serializer):
        board = get_object_or_404(
            Board, pk=serializer.validated_data["board"].pk, owner=self.request.user
        )
        column = serializer.validated_data["column"]
        if column.board_id != board.pk:
            raise ValidationError({"column": "Column must belong to the board."})
        serializer.save(board=board)

    def perform_update(self, serializer):
        raise ValidationError("Card edits require a versioned command.")

    @action(detail=True, methods=["post"])
    def move(self, request, pk=None):
        card = self.get_object()
        data = MoveSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            card = move_card(actor=request.user, card_id=card.pk, **data.validated_data)
        except DjangoPermissionDenied as exc:
            raise PermissionDenied(str(exc)) from exc
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages) from exc
        except Card.DoesNotExist as exc:
            raise NotFound() from exc
        return Response(self.get_serializer(card).data, status=status.HTTP_200_OK)
