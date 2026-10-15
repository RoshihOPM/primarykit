"""Transaction-safe role mutations, branch grants and invitations."""

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.core.audit import record_audit_event

from .models import Branch, BranchAccess, Invitation, Membership, Organization
from .permissions import get_active_membership


def _can_manage(actor_membership, target_role, new_role=None):
    if actor_membership.role == Membership.Role.OWNER:
        return
    if actor_membership.role != Membership.Role.ADMIN:
        raise PermissionDenied("Only owners and admins manage members.")
    if target_role in (Membership.Role.OWNER, Membership.Role.ADMIN) or new_role in (
        Membership.Role.OWNER,
        Membership.Role.ADMIN,
    ):
        raise PermissionDenied("Only owners may manage privileged roles.")


def _preserve_owner(organization, member, *, new_role=None, deactivate=False):
    if member.role != Membership.Role.OWNER or not member.is_active:
        return
    if not deactivate and new_role == Membership.Role.OWNER:
        return
    owners = Membership.objects.filter(
        organization=organization, role=Membership.Role.OWNER, is_active=True
    ).count()
    if owners <= 1:
        raise ValidationError({"role": "An organization must retain an active owner."})


@transaction.atomic
def create_organization(*, actor, slug, name):
    organization = Organization.objects.create(slug=slug, name=name)
    Membership.objects.create(user=actor, organization=organization, role=Membership.Role.OWNER)
    record_audit_event(
        actor=actor,
        action="organizations.created",
        target_type="organizations.Organization",
        target_id=organization.pk,
    )
    return organization


@transaction.atomic
def update_membership(*, actor, organization, membership_id, new_role=None, deactivate=False):
    org = Organization.objects.select_for_update().get(pk=organization.pk)
    manager = get_active_membership(user=actor, organization=org)
    member = (
        Membership.objects.select_for_update()
        .filter(organization=org, pk=membership_id, is_active=True)
        .first()
    )
    if not member:
        raise ValidationError({"member": "Active membership does not exist."})
    _can_manage(manager, member.role, new_role)
    _preserve_owner(org, member, new_role=new_role, deactivate=deactivate)
    before_role = member.role
    if new_role is not None:
        member.role = new_role
    if deactivate:
        member.is_active = False
        BranchAccess.objects.filter(membership=member).delete()
    member.save(update_fields=("role", "is_active", "updated_at"))
    record_audit_event(
        actor=actor,
        action="organizations.membership.changed",
        target_type="organizations.Membership",
        target_id=member.pk,
        changes={
            "role": {"before": before_role, "after": member.role},
            "active": member.is_active,
        },
    )
    return member


@transaction.atomic
def set_branch_access(*, actor, organization, membership_id, branch_ids):
    org = Organization.objects.select_for_update().get(pk=organization.pk)
    manager = get_active_membership(user=actor, organization=org)
    member = (
        Membership.objects.select_for_update()
        .filter(pk=membership_id, organization=org, is_active=True)
        .first()
    )
    if member is None:
        raise ValidationError({"member": "Active membership does not exist."})
    _can_manage(manager, member.role)
    if member.role in (Membership.Role.OWNER, Membership.Role.ADMIN):
        raise ValidationError({"branches": "Owner and admin have full branch access."})
    branches = list(Branch.objects.filter(organization=org, is_active=True, pk__in=branch_ids))
    if len(branches) != len(branch_ids):
        raise ValidationError({"branches": "Unknown or inactive branch."})
    BranchAccess.objects.filter(membership=member).delete()
    BranchAccess.objects.bulk_create(
        [BranchAccess(membership=member, branch=branch) for branch in branches]
    )
    record_audit_event(
        actor=actor,
        action="organizations.branches.assigned",
        target_type="organizations.Membership",
        target_id=member.pk,
        changes={"branch_count": len(branches)},
    )
    return member


@transaction.atomic
def create_invitation(*, actor, organization, invitee, role):
    org = Organization.objects.select_for_update().get(pk=organization.pk)
    manager = get_active_membership(user=actor, organization=org)
    _can_manage(manager, role, role)
    if role == Membership.Role.OWNER:
        raise ValidationError({"role": "Owner role must be assigned by an existing owner."})
    if not invitee.is_active or not invitee.email_verified:
        raise ValidationError({"invitee": "Recipient must have a verified account."})
    existing = Membership.objects.filter(organization=org, user=invitee, is_active=True)
    if existing.exists():
        raise ValidationError({"invitee": "User is already a member."})
    # Remove expired pending invitations under organization row lock.
    Invitation.objects.filter(
        organization=org,
        invitee=invitee,
        state=Invitation.State.PENDING,
        expires_at__lte=timezone.now(),
    ).update(state=Invitation.State.REVOKED)
    if Invitation.objects.filter(
        organization=org, invitee=invitee, state=Invitation.State.PENDING
    ).exists():
        raise ValidationError({"invitee": "Pending invitation already exists."})
    invite = Invitation.objects.create(
        organization=org, invitee=invitee, invited_by=actor, role=role
    )
    record_audit_event(
        actor=actor,
        action="organizations.invitation.created",
        target_type="organizations.Invitation",
        target_id=invite.pk,
    )
    return invite


@transaction.atomic
def accept_invitation(*, actor, invitation_id):
    invitation = Invitation.objects.filter(pk=invitation_id, invitee=actor).first()
    if invitation is None:
        raise ValidationError({"invitation": "Invitation does not exist."})
    org = Organization.objects.select_for_update().get(pk=invitation.organization_id)
    invitation = Invitation.objects.select_for_update().get(pk=invitation.pk)
    if (
        not org.is_active
        or invitation.state != Invitation.State.PENDING
        or invitation.expires_at <= timezone.now()
        or not actor.is_active
        or not actor.email_verified
    ):
        raise ValidationError({"invitation": "Invitation is no longer valid."})
    membership = Membership.objects.select_for_update().filter(organization=org, user=actor).first()
    if membership and membership.is_active:
        raise ValidationError({"invitation": "Already a member."})
    if membership:
        membership.role = invitation.role
        membership.is_active = True
        membership.save(update_fields=("role", "is_active", "updated_at"))
    else:
        membership = Membership.objects.create(organization=org, user=actor, role=invitation.role)
    invitation.state = Invitation.State.ACCEPTED
    invitation.save(update_fields=("state", "updated_at"))
    record_audit_event(
        actor=actor,
        action="organizations.invitation.accepted",
        target_type="organizations.Invitation",
        target_id=invitation.pk,
    )
    return membership


@transaction.atomic
def revoke_invitation(*, actor, organization, invitation_id):
    org = Organization.objects.select_for_update().get(pk=organization.pk)
    manager = get_active_membership(user=actor, organization=org)
    invite = Invitation.objects.select_for_update().filter(
        organization=org, pk=invitation_id, state=Invitation.State.PENDING
    ).first()
    if invite is None:
        raise ValidationError({"invitation": "Pending invitation does not exist."})
    _can_manage(manager, invite.role, invite.role)
    invite.state = Invitation.State.REVOKED
    invite.save(update_fields=("state", "updated_at"))
    record_audit_event(
        actor=actor,
        action="organizations.invitation.revoked",
        target_type="organizations.Invitation",
        target_id=invite.pk,
    )
