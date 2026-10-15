"""Company membership and branch access. Django Groups are not tenant-scoped."""

from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.models import UUIDTimestampedModel


def invitation_expiry():
    return timezone.now() + timedelta(days=7)


class Organization(UUIDTimestampedModel):
    slug = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)


class Membership(UUIDTimestampedModel):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        MANAGER = "manager", "Manager"
        MEMBER = "member", "Member"

    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="memberships"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="organization_memberships"
    )
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "user"), name="org_membership_org_user_uniq"
            )
        ]
        indexes = [models.Index(fields=["user", "is_active"], name="org_member_user_active_idx")]


class Branch(UUIDTimestampedModel):
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="branches"
    )
    code = models.SlugField(max_length=80)
    name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("organization", "code"), name="org_branch_code_uniq")
        ]
        ordering = ("code",)


class BranchAccess(models.Model):
    membership = models.ForeignKey(
        Membership, on_delete=models.CASCADE, related_name="branch_access"
    )
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="member_access")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("membership", "branch"), name="org_branch_access_uniq")
        ]


class Invitation(UUIDTimestampedModel):
    class State(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REVOKED = "revoked", "Revoked"

    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="invitations"
    )
    invitee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="organization_invitations"
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    role = models.CharField(max_length=10, choices=Membership.Role.choices)
    state = models.CharField(max_length=12, choices=State.choices, default=State.PENDING)
    expires_at = models.DateTimeField(default=invitation_expiry)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "invitee"),
                condition=Q(state="pending"),
                name="org_invite_one_pending_per_user",
            ),
        ]
        indexes = [
            models.Index(fields=["invitee", "state"], name="org_invite_inbox_idx"),
        ]
