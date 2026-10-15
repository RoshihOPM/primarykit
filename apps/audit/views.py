import uuid

from django.utils.dateparse import parse_datetime
from rest_framework import mixins, viewsets
from rest_framework.exceptions import ValidationError

from apps.users.permissions import IsActiveSuperuser

from .models import AuditEvent
from .serializers import AuditEventSerializer


class AuditEventViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = AuditEventSerializer
    permission_classes = (IsActiveSuperuser,)
    queryset = AuditEvent.objects.all()
    http_method_names = ("get", "head", "options")

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        for field in ("action", "target_type", "target_id"):
            value = params.get(field)
            if value:
                if len(value) > 128:
                    raise ValidationError({field: "Filter is too long."})
                qs = qs.filter(**{field: value})
        if params.get("actor"):
            try:
                actor_id = uuid.UUID(params["actor"])
            except ValueError as exc:
                raise ValidationError({"actor": "Invalid user ID."}) from exc
            qs = qs.filter(actor_id=actor_id)
        for key, lookup in (("from", "occurred_at__gte"), ("to", "occurred_at__lte")):
            if params.get(key):
                value = parse_datetime(params[key])
                if value is None or value.tzinfo is None:
                    raise ValidationError({key: "Expected ISO 8601 date and time with timezone."})
                qs = qs.filter(**{lookup: value})
        return qs
