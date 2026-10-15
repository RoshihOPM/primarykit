"""Composable abstract models. Only opt in to soft deletion where appropriate."""

import uuid

from django.db import models
from django.utils import timezone

from .managers import ActiveManager, AllObjectsManager


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UUIDTimestampedModel(UUIDModel, TimestampedModel):
    """General purpose UUID + timestamp base (without deletion behavior)."""

    class Meta:
        abstract = True


class SoftDeleteModel(models.Model):
    """Opt-in soft deletion; queryset.delete() does not cascade or emit signals."""

    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = ActiveManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True
        default_manager_name = "objects"
        base_manager_name = "all_objects"

    def delete(self, using=None, keep_parents=False):
        """Idempotently mark this row as deleted. Use hard_delete for physical deletion."""
        if self._state.adding:
            raise ValueError("Cannot soft-delete an unsaved instance")
        deleted_at = timezone.now()
        queryset = type(self).all_objects.using(using or self._state.db)
        count = queryset.filter(pk=self.pk, deleted_at__isnull=True).update(deleted_at=deleted_at)
        if count:
            self.deleted_at = deleted_at
        return count, {self._meta.label: count}

    def restore(self):
        """Restore a previously soft-deleted row (may raise IntegrityError)."""
        if self._state.adding:
            raise ValueError("Cannot restore an unsaved instance")
        queryset = type(self).all_objects.using(self._state.db)
        count = queryset.filter(pk=self.pk, deleted_at__isnull=False).update(deleted_at=None)
        if count:
            self.deleted_at = None
        return bool(count)

    def hard_delete(self, using=None, keep_parents=False):
        return super().delete(using=using, keep_parents=keep_parents)


class SoftDeleteUUIDTimestampedModel(SoftDeleteModel, UUIDTimestampedModel):
    """Convenience base: UUID + timestamps + opt-in soft deletion."""

    class Meta:
        abstract = True
        default_manager_name = "objects"
        base_manager_name = "all_objects"
