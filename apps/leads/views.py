from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Lead
from .serializers import LeadSerializer, LeadTransitionSerializer
from .services import transition_lead


class LeadViewSet(viewsets.ModelViewSet):
    permission_classes = (IsAuthenticated,)
    serializer_class = LeadSerializer
    http_method_names = ("get", "post", "patch", "head", "options")

    def get_queryset(self):
        return Lead.objects.filter(owner=self.request.user).order_by("-created_at")

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        self.get_object()
        data = LeadTransitionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        lead = transition_lead(actor=request.user, lead_id=pk, **data.validated_data)
        return Response(self.get_serializer(lead).data)
