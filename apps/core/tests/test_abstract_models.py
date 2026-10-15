"""Integration-style behavior checks for abstract model combinations."""

from itertools import count

import pytest
from django.db import IntegrityError, connection, models

from apps.core.models import SoftDeleteUUIDTimestampedModel, UUIDTimestampedModel

_model_index = count()


@pytest.fixture
def record_model():
    """Use a distinct temporary model per test to avoid Django registry reloads."""
    index = next(_model_index)
    meta = type(
        "Meta",
        (),
        {"app_label": "core", "db_table": f"primarykit_soft_delete_test_{index}"},
    )
    Record = type(
        f"TemporaryRecord{index}",
        (SoftDeleteUUIDTimestampedModel,),
        {
            "__module__": __name__,
            "Meta": meta,
            "name": models.CharField(max_length=100, unique=True),
        },
    )

    with connection.schema_editor() as editor:
        editor.create_model(Record)
    try:
        yield Record
    finally:
        with connection.schema_editor() as editor:
            editor.delete_model(Record)


@pytest.mark.django_db(transaction=True)
def test_soft_delete_instance_and_restore(record_model):
    record = record_model.objects.create(name="test")
    original_id = record.id

    assert record.deleted_at is None
    assert record.created_at is not None
    assert record.updated_at is not None
    assert record.delete()[0] == 1
    assert record.delete()[0] == 0  # idempotent
    assert record_model.objects.filter(pk=original_id).count() == 0
    assert record_model.all_objects.filter(pk=original_id).count() == 1
    assert record_model.all_objects.deleted().count() == 1
    assert record.restore() is True
    assert record_model.objects.filter(pk=original_id).exists()


@pytest.mark.django_db(transaction=True)
def test_queryset_soft_delete_and_hard_delete(record_model):
    first = record_model.objects.create(name="first")
    record_model.objects.create(name="second")

    count, _ = record_model.objects.filter(pk=first.pk).delete()
    assert count == 1
    assert record_model.objects.count() == 1
    assert record_model.all_objects.count() == 2
    assert record_model.all_objects.deleted().restore() == 1
    assert record_model.objects.count() == 2
    assert record_model.all_objects.filter(pk=first.pk).hard_delete()[0] == 1
    assert record_model.all_objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_soft_delete_does_not_automatically_release_unique_value(record_model):
    first = record_model.objects.create(name="reserved")
    first.delete()

    with pytest.raises(IntegrityError):
        record_model.objects.create(name="reserved")


def test_base_without_soft_delete_is_available():
    assert UUIDTimestampedModel._meta.abstract
    assert not hasattr(UUIDTimestampedModel, "deleted_at")
