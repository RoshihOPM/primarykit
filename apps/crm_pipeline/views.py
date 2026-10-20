"""Opt-in mapping endpoints, always scoped by the authenticated owner."""

from rest_framework import mixins, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import DealCardLink
from .serializers import BindDealCardSerializer, DealCardLinkSerializer
from .services import bind_deal_card


class DealCardLinkViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = (IsAuthenticated,)
    serializer_class = DealCardLinkSerializer
    http_method_names = ("get", "post", "head", "options")

    def get_queryset(self):
        return DealCardLink.objects.filter(owner=self.request.user).order_by("-created_at", "-pk")

    def create(self, request, *args, **kwargs):
        serializer = BindDealCardSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        link = bind_deal_card(actor=request.user, **serializer.validated_data)
        return Response(self.get_serializer(link).data, status=status.HTTP_201_CREATED)
