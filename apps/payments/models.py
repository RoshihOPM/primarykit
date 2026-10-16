"""Provider-neutral intent and immutable trusted reconciliation event."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.models import UUIDTimestampedModel


class PaymentIntent(UUIDTimestampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        CANCELED = "canceled", "Canceled"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    amount_minor = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3)
    source_order_id = models.UUIDField(null=True, blank=True, db_index=True)
    idempotency_key = models.CharField(max_length=128)
    fingerprint = models.CharField(max_length=64)
    settled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("owner", "idempotency_key"), name="payments_owner_idempotency_unique"
            ),
            models.UniqueConstraint(
                fields=("owner", "source_order_id"),
                condition=Q(status="succeeded", source_order_id__isnull=False),
                name="payments_one_successful_order",
            ),
        ]


class ImmutablePaymentEventQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Payment events are immutable.")

    def delete(self):
        raise ValidationError("Payment events are immutable.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError("Payment events are immutable.")


class PaymentEvent(UUIDTimestampedModel):
    """Only privileged reconciliation service may append settlement evidence."""

    intent = models.ForeignKey(PaymentIntent, on_delete=models.PROTECT, related_name="events")
    event_key = models.CharField(max_length=128, unique=True)
    outcome = models.CharField(max_length=12, choices=(
        ("succeeded", "Succeeded"), ("failed", "Failed"),
    ))
    amount_minor = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )

    objects = ImmutablePaymentEventQuerySet.as_manager()

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Payment events are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Payment events cannot be deleted.")
