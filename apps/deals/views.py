"""Independent, owner-scoped Deal API."""

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Deal
from .serializers import DealEditSerializer, DealSerializer, DealTransitionSerializer
from .services import edit_deal, transition_deal


class DealViewSet(viewsets.ModelViewSet):
    permission_classes = (IsAuthenticated,)
    serializer_class = DealSerializer
    http_method_names = ("get", "post", "patch", "head", "options")

    def get_queryset(self):
        return Deal.objects.filter(owner=self.request.user).order_by("-created_at")

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def partial_update(self, request, *args, **kwargs):
        deal = self.get_object()
        payload = DealEditSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        changes = dict(payload.validated_data)
        expected_version = changes.pop("expected_version")
        updated = edit_deal(
            actor=request.user,
            deal_id=deal.pk,
            expected_version=expected_version,
            changes=changes,
        )
        return Response(self.get_serializer(updated).data)

    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        deal = self.get_object()
        payload = DealTransitionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        updated = transition_deal(actor=request.user, deal_id=deal.pk, **payload.validated_data)
        return Response(self.get_serializer(updated).data)
