"""Optional transition journal; client aggregates own their state and migrations."""

from django.db import models


class WorkflowStateMixin(models.Model):
    """Optional fields for a client-owned aggregate; set the initial state explicitly."""

    workflow_state = models.CharField(max_length=64)
    workflow_version = models.PositiveIntegerField(default=0)

    class Meta:
        abstract = True


class WorkflowTransitionHistory(models.Model):
    """Immutable-in-service event history scoped to a client-owned aggregate.

    The caller must enforce aggregate ownership. There is intentionally no
    public API and no generic lookup by user-provided aggregate identifiers.
    """

    event_id = models.UUIDField(primary_key=True, editable=False)
    scope = models.CharField(max_length=80)
    aggregate_id = models.CharField(max_length=128)
    version = models.PositiveIntegerField()
    action = models.CharField(max_length=64)
    from_state = models.CharField(max_length=64)
    to_state = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("scope", "aggregate_id", "version"),
                name="wf_scope_aggregate_version_uq",
            )
        ]
