"""Opt-in soft deletion; default filtering is intentionally explicit and documented."""

from django.db import models
from django.utils import timezone


class SoftDeleteQuerySet(models.QuerySet):
    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def deleted(self):
        return self.filter(deleted_at__isnull=False)

    def delete(self):
        """Mark matching active rows deleted; does not cascade or emit delete signals."""
        count = self.alive().update(deleted_at=timezone.now())
        return count, {self.model._meta.label: count}

    def restore(self):
        """Restore matching deleted rows. Caller must handle uniqueness conflicts."""
        return self.deleted().update(deleted_at=None)

    def hard_delete(self):
        """Perform Django's regular delete (including ORM cascades)."""
        return super().delete()


class ActiveManager(models.Manager.from_queryset(SoftDeleteQuerySet)):
    def get_queryset(self):
        return super().get_queryset().alive()


class AllObjectsManager(models.Manager.from_queryset(SoftDeleteQuerySet)):
    """Unfiltered manager for relations, admin operations, and explicit recovery."""
