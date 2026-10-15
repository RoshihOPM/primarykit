from rest_framework import serializers

from .models import AuditEvent


class AuditEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = ("id", "occurred_at", "actor_id", "action", "target_type", "target_id", "changes")
        read_only_fields = fields
