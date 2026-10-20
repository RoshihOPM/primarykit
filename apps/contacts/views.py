"""JWT-only personal contact directory; no destructive DELETE."""

from rest_framework import serializers, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Contact
from .serializers import ContactEditSerializer, ContactSerializer
from .services import edit_contact


class ContactViewSet(viewsets.ModelViewSet):
    permission_classes = (IsAuthenticated,)
    serializer_class = ContactSerializer
    http_method_names = ("get", "post", "patch", "head", "options")

    def get_queryset(self):
        qs = Contact.objects.filter(owner=self.request.user)
        company = self.request.query_params.get("company")
        if company is not None:
            if len(company) > 160:
                raise serializers.ValidationError({"company": "Too long."})
            qs = qs.filter(company=company)
        return qs.order_by("-created_at", "-pk")

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def partial_update(self, request, *args, **kwargs):
        contact = self.get_object()
        serializer = ContactEditSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        changes = dict(serializer.validated_data)
        expected_version = changes.pop("expected_version")
        result = edit_contact(
            actor=request.user,
            contact_id=contact.pk,
            expected_version=expected_version,
            changes=changes,
        )
        return Response(self.get_serializer(result).data)
