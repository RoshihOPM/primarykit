import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.organizations.models import Branch, BranchAccess, Invitation, Membership, Organization
from apps.users.models import User

pytestmark = pytest.mark.django_db


def account(email):
    user = User.objects.create_user(
        email=email, password="A-long-password-8123", email_verified=True
    )
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return user, api


def setup_organizations():
    owner1, api1 = account("owner-a@example.test")
    owner2, api2 = account("owner-b@example.test")
    outsider, api3 = account("outsider@example.test")
    first = api1.post(reverse("org-list"), {"name": "One", "slug": "one"}, format="json")
    second = api2.post(reverse("org-list"), {"name": "Two", "slug": "two"}, format="json")
    assert first.status_code == second.status_code == 201
    return (owner1, api1, first.data["id"]), (owner2, api2, second.data["id"]), (outsider, api3)


def test_create_grants_creator_owner_and_does_not_accept_privileged_fields():
    owner, api = account("founder@example.test")
    response = api.post(
        reverse("org-list"),
        {"name": "Example", "slug": "example", "is_active": False, "owner": "other"},
        format="json",
    )
    assert response.status_code == 201, response.data
    org = Organization.objects.get(pk=response.data["id"])
    assert org.is_active
    membership = Membership.objects.get(organization=org, user=owner)
    assert membership.role == Membership.Role.OWNER
    assert api.get(reverse("org-list")).data["count"] == 1


def test_cross_company_org_and_branch_idor():
    (owner1, api1, org1), (_, api2, org2), (_, stranger) = setup_organizations()
    created = api1.post(
        reverse("org-branches", kwargs={"org_id": org1}),
        {"code": "central", "name": "Central", "organization": org2},
        format="json",
    )
    assert created.status_code == 201, created.data
    branch = Branch.objects.get(pk=created.data["id"])
    assert str(branch.organization_id) == org1
    assert stranger.get(reverse("org-detail", kwargs={"pk": org1})).status_code == 404
    assert api2.get(reverse("org-detail", kwargs={"pk": org1})).status_code == 404
    assert api2.get(reverse("org-branches", kwargs={"org_id": org1})).status_code == 404
    assert (
        api2.get(
            reverse("org-branch-detail", kwargs={"org_id": org2, "branch_id": branch.pk})
        ).status_code
        == 404
    )
    assert (
        api2.patch(reverse("org-detail", kwargs={"pk": org1}), {"name": "Hacked"}).status_code
        == 404
    )
    assert (
        api1.get(
            reverse("org-branch-detail", kwargs={"org_id": org1, "branch_id": branch.pk})
        ).status_code
        == 200
    )


def test_invitation_requires_explicit_acceptance_and_is_person_bound():
    (owner, api, org_id), (_, other_api, _), (candidate, candidate_api) = setup_organizations()
    create_url = reverse("org-invitations", kwargs={"org_id": org_id})
    response = api.post(create_url, {"invitee": str(candidate.pk), "role": "member"}, format="json")
    assert response.status_code == 201, response.data
    inv_id = response.data["id"]
    assert not Membership.objects.filter(organization_id=org_id, user=candidate).exists()
    assert (
        other_api.post(
            reverse("org-invitation-accept", kwargs={"invitation_id": inv_id})
        ).status_code
        == 400
    )
    assert candidate_api.get(reverse("org-my-invitations")).data[0]["id"] == inv_id
    accepted = candidate_api.post(
        reverse("org-invitation-accept", kwargs={"invitation_id": inv_id})
    )
    assert accepted.status_code == 200
    assert accepted.data["role"] == "member"
    assert (
        candidate_api.post(
            reverse("org-invitation-accept", kwargs={"invitation_id": inv_id})
        ).status_code
        == 400
    )
    assert candidate_api.get(reverse("org-detail", kwargs={"pk": org_id})).status_code == 200


def test_member_branch_grants_and_cross_org_denial():
    (owner, api, org_id), (_, api2, org2), (member, member_api) = setup_organizations()
    local = api.post(
        reverse("org-branches", kwargs={"org_id": org_id}),
        {"code": "local", "name": "Local"},
        format="json",
    ).data["id"]
    other = api.post(
        reverse("org-branches", kwargs={"org_id": org_id}),
        {"code": "other", "name": "Other"},
        format="json",
    ).data["id"]
    foreign = api2.post(
        reverse("org-branches", kwargs={"org_id": org2}),
        {"code": "foreign", "name": "Foreign"},
        format="json",
    ).data["id"]
    invitation = api.post(
        reverse("org-invitations", kwargs={"org_id": org_id}),
        {"invitee": str(member.pk), "role": "member"},
        format="json",
    ).data["id"]
    assert (
        member_api.post(
            reverse("org-invitation-accept", kwargs={"invitation_id": invitation})
        ).status_code
        == 200
    )
    mid = str(Membership.objects.get(organization_id=org_id, user=member).pk)
    assert member_api.get(reverse("org-branches", kwargs={"org_id": org_id})).data == []
    grant_url = reverse("org-member-branches", kwargs={"org_id": org_id, "member_id": mid})
    assert api.put(grant_url, {"branch_ids": [local, foreign]}, format="json").status_code == 400
    assert not BranchAccess.objects.filter(membership_id=mid).exists()
    assert api.put(grant_url, {"branch_ids": [local]}, format="json").status_code == 204
    assert len(member_api.get(reverse("org-branches", kwargs={"org_id": org_id})).data) == 1
    assert (
        member_api.get(
            reverse("org-branch-detail", kwargs={"org_id": org_id, "branch_id": other})
        ).status_code
        == 404
    )
    assert (
        member_api.get(
            reverse("org-branch-detail", kwargs={"org_id": org_id, "branch_id": local})
        ).status_code
        == 200
    )


def test_last_owner_cannot_leave_or_demote_self():
    (owner, api, org_id), (_, _, _), _ = setup_organizations()
    member = Membership.objects.get(organization_id=org_id, user=owner)
    url = reverse("org-member-detail", kwargs={"org_id": org_id, "member_id": member.pk})
    assert api.patch(url, {"role": "member"}, format="json").status_code == 400
    assert api.delete(url).status_code == 400
    member.refresh_from_db()
    assert member.role == "owner" and member.is_active


def test_admin_cannot_elevate_privileges_or_remove_owner():
    (owner, api, org_id), (_, _, _), (candidate, member_api) = setup_organizations()
    invitation = api.post(
        reverse("org-invitations", kwargs={"org_id": org_id}),
        {"invitee": str(candidate.pk), "role": "admin"},
        format="json",
    )
    assert invitation.status_code == 201
    member_api.post(
        reverse("org-invitation-accept", kwargs={"invitation_id": invitation.data["id"]})
    )
    member = Membership.objects.get(organization_id=org_id, user=candidate)
    first = Membership.objects.get(organization_id=org_id, user=owner)
    url = reverse("org-member-detail", kwargs={"org_id": org_id, "member_id": first.pk})
    assert member_api.patch(url, {"role": "member"}, format="json").status_code == 403
    assert member_api.delete(url).status_code == 403
    own_url = reverse("org-member-detail", kwargs={"org_id": org_id, "member_id": member.pk})
    assert member_api.patch(own_url, {"role": "owner"}, format="json").status_code == 403
    assert (
        member_api.post(
            reverse("org-invitations", kwargs={"org_id": org_id}),
            {"invitee": str(owner.pk), "role": "owner"},
            format="json",
        ).status_code
        == 400
    )


def test_org_manager_cannot_manage_roles_or_other_members():
    (owner, api, org_id), (_, _, _), (manager, manager_api) = setup_organizations()
    response = api.post(
        reverse("org-invitations", kwargs={"org_id": org_id}),
        {"invitee": str(manager.pk), "role": "manager"},
        format="json",
    )
    manager_api.post(
        reverse("org-invitation-accept", kwargs={"invitation_id": response.data["id"]})
    )
    assert manager_api.get(reverse("org-members", kwargs={"org_id": org_id})).status_code == 403
    assert (
        manager_api.post(
            reverse("org-invitations", kwargs={"org_id": org_id}),
            {"invitee": str(owner.pk), "role": "member"},
            format="json",
        ).status_code
        == 403
    )


def test_expired_invitation_cannot_be_accepted():
    from datetime import timedelta

    from django.utils import timezone

    (_, api, org_id), (_, _, _), (candidate, recipient) = setup_organizations()
    result = api.post(
        reverse("org-invitations", kwargs={"org_id": org_id}),
        {"invitee": str(candidate.pk), "role": "member"},
        format="json",
    )
    inv = Invitation.objects.get(pk=result.data["id"])
    inv.expires_at = timezone.now() - timedelta(minutes=1)
    inv.save(update_fields=["expires_at"])
    assert (
        recipient.post(
            reverse("org-invitation-accept", kwargs={"invitation_id": inv.pk})
        ).status_code
        == 400
    )
    assert not Membership.objects.filter(organization_id=org_id, user=candidate).exists()


def test_owner_can_revoke_pending_invitation_and_recipient_cannot_accept():
    (_, api, org_id), (_, api_other, _), (recipient, recipient_api) = setup_organizations()
    created = api.post(
        reverse("org-invitations", kwargs={"org_id": org_id}),
        {"invitee": str(recipient.pk), "role": "member"},
        format="json",
    )
    assert created.status_code == 201
    invitation_id = created.data["id"]
    url = reverse(
        "org-invitation-detail", kwargs={"org_id": org_id, "invitation_id": invitation_id}
    )
    assert api_other.delete(url).status_code == 404
    assert api.delete(url).status_code == 204
    assert (
        recipient_api.post(
            reverse("org-invitation-accept", kwargs={"invitation_id": invitation_id})
        ).status_code
        == 400
    )
    assert not Membership.objects.filter(organization_id=org_id, user=recipient).exists()


def test_second_owner_allows_safe_transfer_of_ownership():
    (owner, api, org_id), (_, _, _), (recipient, recipient_api) = setup_organizations()
    invited = api.post(
        reverse("org-invitations", kwargs={"org_id": org_id}),
        {"invitee": str(recipient.pk), "role": "admin"},
        format="json",
    )
    assert invited.status_code == 201
    accepted = recipient_api.post(
        reverse("org-invitation-accept", kwargs={"invitation_id": invited.data["id"]})
    )
    assert accepted.status_code == 200
    new_owner = Membership.objects.get(organization_id=org_id, user=recipient)
    old_owner = Membership.objects.get(organization_id=org_id, user=owner)
    promote = api.patch(
        reverse("org-member-detail", kwargs={"org_id": org_id, "member_id": new_owner.pk}),
        {"role": "owner"},
        format="json",
    )
    assert promote.status_code == 200
    self_deactivate = api.delete(
        reverse("org-member-detail", kwargs={"org_id": org_id, "member_id": old_owner.pk})
    )
    assert self_deactivate.status_code == 204
    old_owner.refresh_from_db()
    new_owner.refresh_from_db()
    assert not old_owner.is_active
    assert new_owner.is_active and new_owner.role == "owner"
    assert api.get(reverse("org-detail", kwargs={"pk": org_id})).status_code == 404
    assert recipient_api.get(reverse("org-detail", kwargs={"pk": org_id})).status_code == 200


def test_invitation_to_disabled_or_unverified_account_is_rejected():
    (_, owner_api, org_id), (_, _, _), (invitee, _) = setup_organizations()
    invitee.email_verified = False
    invitee.save(update_fields=["email_verified"])
    url = reverse("org-invitations", kwargs={"org_id": org_id})
    assert owner_api.post(
        url, {"invitee": str(invitee.pk), "role": "member"}, format="json"
    ).status_code == 400
    invitee.email_verified = True
    invitee.is_active = False
    invitee.save(update_fields=["email_verified", "is_active"])
    assert owner_api.post(
        url, {"invitee": str(invitee.pk), "role": "member"}, format="json"
    ).status_code == 400
    assert not Invitation.objects.filter(organization_id=org_id, invitee=invitee).exists()


def test_membership_and_branch_assignment_cannot_cross_tenants():
    (owner, owner_api, first_id), (other_owner, other_api, second_id), _ = setup_organizations()
    invitee, invitee_api = account("cross-tenant@example.test")
    pending = owner_api.post(
        reverse("org-invitations", kwargs={"org_id": first_id}),
        {"invitee": str(invitee.pk), "role": "member"}, format="json",
    )
    assert pending.status_code == 201
    assert invitee_api.post(
        reverse("org-invitation-accept", kwargs={"invitation_id": pending.data["id"]})
    ).status_code == 200
    target = Membership.objects.get(organization_id=first_id, user=invitee)
    foreign = other_api.post(
        reverse("org-branches", kwargs={"org_id": second_id}),
        {"code": "foreign", "name": "Foreign"},
        format="json",
    )
    assert foreign.status_code == 201
    wrong_org_member = reverse(
        "org-member-detail", kwargs={"org_id": second_id, "member_id": target.pk}
    )
    assert other_api.patch(wrong_org_member, {"role": "admin"}).status_code == 400
    assert other_api.put(
        reverse(
            "org-member-branches",
            kwargs={"org_id": second_id, "member_id": target.pk},
        ),
        {"branch_ids": [foreign.data["id"]]},
        format="json",
    ).status_code == 400
    assert owner_api.put(
        reverse(
            "org-member-branches",
            kwargs={"org_id": first_id, "member_id": target.pk},
        ),
        {"branch_ids": [foreign.data["id"]]},
        format="json",
    ).status_code == 400
    assert not BranchAccess.objects.filter(membership=target).exists()
    target.refresh_from_db()
    assert target.role == "member"


def test_duplicate_pending_invite_does_not_create_second_invitation():
    (_, api, org_id), _, (invitee, _) = setup_organizations()
    url = reverse("org-invitations", kwargs={"org_id": org_id})
    payload = {"invitee": str(invitee.pk), "role": "member"}
    assert api.post(url, payload, format="json").status_code == 201
    assert api.post(url, payload, format="json").status_code == 400
    assert Invitation.objects.filter(organization_id=org_id, invitee=invitee).count() == 1
