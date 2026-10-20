from django.db import transaction
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Lead
from .serializers import LeadEditSerializer, LeadSerializer, LeadTransitionSerializer
from .services import create_lead, edit_lead, transition_lead


class LeadViewSet(viewsets.ModelViewSet):
    permission_classes = (IsAuthenticated,)
    serializer_class = LeadSerializer
    http_method_names = ("get", "post", "patch", "head", "options")

    def get_queryset(self):
        qs = Lead.objects.filter(owner=self.request.user)
        query = self.request.query_params
        status = query.get("status")
        source = query.get("source")
        if status is not None:
            if status not in Lead.Status.values:
                raise serializers.ValidationError({"status": "Invalid status."})
            qs = qs.filter(status=status)
        if source is not None:
            if len(source) > 80:
                raise serializers.ValidationError({"source": "Too long."})
            qs = qs.filter(source=source)
        return qs.order_by("-created_at", "-pk")

    @transaction.atomic
    def perform_create(self, serializer):
        serializer.instance = create_lead(actor=self.request.user, data=serializer.validated_data)

    def partial_update(self, request, *args, **kwargs):
        lead = self.get_object()
        serializer = LeadEditSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        changes = dict(serializer.validated_data)
        expected_version = changes.pop("expected_version")
        updated = edit_lead(
            actor=request.user,
            lead_id=lead.pk,
            expected_version=expected_version,
            changes=changes,
        )
        return Response(self.get_serializer(updated).data)

    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        self.get_object()
        data = LeadTransitionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        lead = transition_lead(actor=request.user, lead_id=pk, **data.validated_data)
        return Response(self.get_serializer(lead).data)
