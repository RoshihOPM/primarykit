"""Strictly private HTTP endpoints; no implicit notifications or subscriptions."""

from rest_framework import mixins, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from .serializers import (
    FavoriteCreateSerializer,
    FavoriteReadSerializer,
    SavedSearchReadSerializer,
    SavedSearchWriteSerializer,
)
from .services import (
    add_favorite,
    create_search,
    delete_search,
    owned_searches,
    remove_favorite,
    update_search,
    visible_favorites,
)


class PersonalThrottleMixin:
    throttle_classes = (ScopedRateThrottle,)

    def get_throttles(self):
        self.throttle_scope = (
            "favorites_write" if self.request.method in {"POST", "PATCH", "DELETE"}
            else "favorites_read"
        )
        return super().get_throttles()


class FavoriteViewSet(
    PersonalThrottleMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = (IsAuthenticated,)
    serializer_class = FavoriteReadSerializer
    http_method_names = ("get", "post", "delete", "head", "options")

    def get_queryset(self):
        return visible_favorites(self.request.user)

    def create(self, request, *args, **kwargs):
        incoming = FavoriteCreateSerializer(data=request.data)
        incoming.is_valid(raise_exception=True)
        favorite, created = add_favorite(
            actor=request.user, listing_id=incoming.validated_data["listing_id"]
        )
        return Response(
            self.get_serializer(favorite).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def destroy(self, request, *args, **kwargs):
        remove_favorite(actor=request.user, favorite_id=kwargs["pk"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class SavedSearchViewSet(
    PersonalThrottleMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = (IsAuthenticated,)
    serializer_class = SavedSearchReadSerializer
    http_method_names = ("get", "post", "patch", "delete", "head", "options")

    def get_queryset(self):
        return owned_searches(self.request.user)

    def create(self, request, *args, **kwargs):
        incoming = SavedSearchWriteSerializer(data=request.data)
        incoming.is_valid(raise_exception=True)
        record = create_search(actor=request.user, **incoming.validated_data)
        return Response(self.get_serializer(record).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        incoming = SavedSearchWriteSerializer(data=request.data, partial=True)
        incoming.is_valid(raise_exception=True)
        record = update_search(
            actor=request.user, search_id=kwargs["pk"], changes=incoming.validated_data
        )
        return Response(self.get_serializer(record).data)

    def destroy(self, request, *args, **kwargs):
        delete_search(actor=request.user, search_id=kwargs["pk"])
        return Response(status=status.HTTP_204_NO_CONTENT)
