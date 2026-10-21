"""Immutable initial schema of PostgreSQL-backed jobs and schedules for new clients."""

import uuid

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="BackgroundJob",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("namespace", models.CharField(default="default", max_length=80)),
                ("code", models.CharField(max_length=100)),
                ("payload", models.JSONField()),
                ("idempotency_key", models.CharField(blank=True, max_length=128, null=True)),
                ("status", models.CharField(
                    choices=[("pending", "Pending"), ("running", "Running"), ("succeeded", "Succeeded"), ("failed", "Failed")],
                    default="pending", max_length=16,
                )),
                ("available_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("max_attempts", models.PositiveSmallIntegerField(default=5)),
                ("locked_at", models.DateTimeField(blank=True, null=True)),
                ("lease_token", models.UUIDField(blank=True, null=True)),
                ("last_error", models.CharField(blank=True, default="", max_length=160)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "indexes": [
                    models.Index(fields=["status", "available_at", "created_at"], name="tasks_ready_idx"),
                    models.Index(fields=["status", "locked_at"], name="tasks_lease_idx"),
                ],
                "constraints": [
                    models.CheckConstraint(condition=models.Q(max_attempts__gte=1) & models.Q(max_attempts__lte=10), name="tasks_max_attempts_valid"),
                    models.CheckConstraint(condition=models.Q(attempts__lte=models.F("max_attempts")), name="tasks_attempts_not_exceeded"),
                    models.UniqueConstraint(fields=("namespace", "idempotency_key"), name="tasks_namespace_idempotency"),
                ],
            },
        ),
        migrations.CreateModel(
            name="JobSchedule",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("namespace", models.CharField(default="default", max_length=80)),
                ("name", models.CharField(max_length=100)),
                ("code", models.CharField(max_length=100)),
                ("payload", models.JSONField()),
                ("timezone_name", models.CharField(default="UTC", max_length=64)),
                ("hour", models.PositiveSmallIntegerField()),
                ("minute", models.PositiveSmallIntegerField()),
                ("weekdays", models.JSONField(blank=True, default=list)),
                ("max_attempts", models.PositiveSmallIntegerField(default=5)),
                ("next_run_at", models.DateTimeField()),
                ("is_enabled", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "indexes": [
                    models.Index(fields=["is_enabled", "next_run_at"], name="tasks_schedule_due_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("namespace", "name"), name="tasks_schedule_name_uniq"),
                    models.CheckConstraint(condition=models.Q(hour__gte=0) & models.Q(hour__lte=23), name="tasks_schedule_hour_valid"),
                    models.CheckConstraint(condition=models.Q(minute__gte=0) & models.Q(minute__lte=59), name="tasks_schedule_minute_valid"),
                    models.CheckConstraint(condition=models.Q(max_attempts__gte=1) & models.Q(max_attempts__lte=10), name="tasks_schedule_attempts_valid"),
                ],
            },
        ),
    ]
