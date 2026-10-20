import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import User

pytestmark = pytest.mark.django_db


def client(email):
    user = User.objects.create_user(email=email, password="strongpass", email_verified=True)
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return api


def test_lead_privacy_and_transitions():
    api = client("leads-owner@example.test")
    other = client("leads-other@example.test")
    url = "/api/v1/leads/"
    created = api.post(url, {"title": "Sales lead", "contact_name": "Customer"})
    assert created.status_code == 201, created.data
    pk = created.data["id"]
    assert other.get(url).data["count"] == 0
    assert other.get(url + pk + "/").status_code == 404
    assert (
        other.post(url + pk + "/transition/", {"status": "won", "expected_version": 0}).status_code
        == 404
    )
    assert (
        api.post(url + pk + "/transition/", {"status": "won", "expected_version": 0}).status_code
        == 400
    )
    qualified = api.post(url + pk + "/transition/", {"status": "qualified", "expected_version": 0})
    assert qualified.status_code == 200
    assert qualified.data["version"] == 1
    assert (
        api.post(url + pk + "/transition/", {"status": "won", "expected_version": 0}).status_code
        == 409
    )
    assert (
        api.post(url + pk + "/transition/", {"status": "won", "expected_version": 1}).status_code
        == 200
    )
    assert api.patch(url + pk + "/", {"status": "new", "version": 0}).status_code == 400
    edited = api.patch(url + pk + "/", {"expected_version": 2, "notes": "Call back"})
    assert edited.status_code == 200
    assert edited.data["version"] == 3
    assert (
        api.patch(url + pk + "/", {"expected_version": 2, "notes": "Lost update"}).status_code
        == 409
    )
    assert (
        other.patch(url + pk + "/", {"expected_version": 3, "notes": "Intrusion"}).status_code
        == 404
    )


def test_lead_filters_and_assignee_policy():
    from apps.leads.models import Lead
    from apps.users.models import User

    owner = User.objects.create_user(
        email="filter-owner@example.test", password="strongpass", email_verified=True
    )
    colleague = User.objects.create_user(
        email="filter-colleague@example.test", password="strongpass", email_verified=True
    )
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(owner).access_token}")
    root = "/api/v1/leads/"
    created = api.post(
        root,
        {"title": "First", "contact_name": "A", "source": "website", "assigned_to": str(owner.pk)},
    )
    assert created.status_code == 201, created.data
    assert created.data["assigned_to"] == str(owner.pk)
    second = api.post(root, {"title": "Second", "contact_name": "B", "source": "referral"})
    assert second.status_code == 201
    assert api.get(root, {"source": "website"}).data["count"] == 1
    assert api.get(root, {"status": "new"}).data["count"] == 2
    assert api.get(root, {"status": "unknown"}).status_code == 400
    assert api.get(root, {"source": "x" * 81}).status_code == 400
    unauthorized = api.patch(
        root + created.data["id"] + "/",
        {"expected_version": 0, "assigned_to": str(colleague.pk)},
    )
    assert unauthorized.status_code == 400
    assert Lead.objects.get(pk=created.data["id"]).version == 0


def test_lead_assignee_requires_active_shared_membership_when_organizations_installed():
    from django.apps import apps

    from apps.users.models import User

    if not apps.is_installed("apps.organizations"):
        pytest.skip("Standalone Leads has no shared organization memberships")
    from apps.organizations.models import Membership, Organization

    owner = User.objects.create_user(email="shared-owner@example.test", password="strongpass")
    colleague = User.objects.create_user(
        email="shared-colleague@example.test", password="strongpass"
    )
    outsider = User.objects.create_user(email="shared-outsider@example.test", password="strongpass")
    organization = Organization.objects.create(slug="shared-leads", name="Shared Leads")
    Membership.objects.create(organization=organization, user=owner, is_active=True)
    other_membership = Membership.objects.create(
        organization=organization, user=colleague, is_active=True
    )
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(owner).access_token}")
    root = "/api/v1/leads/"
    created = api.post(
        root, {"title": "Qualified", "contact_name": "Client", "assigned_to": str(colleague.pk)}
    )
    assert created.status_code == 201, created.data
    assert (
        api.post(
            root,
            {"title": "Unauthorized", "contact_name": "Client", "assigned_to": str(outsider.pk)},
        ).status_code
        == 400
    )
    other_membership.is_active = False
    other_membership.save(update_fields=["is_active"])
    assert (
        api.patch(
            root + created.data["id"] + "/",
            {"expected_version": 0, "assigned_to": str(colleague.pk)},
        ).status_code
        == 400
    )
    # Assignment is metadata, not authorization: the colleague cannot read the lead.
    other_api = APIClient()
    other_api.credentials(
        HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(colleague).access_token}"
    )
    assert other_api.get(root + created.data["id"] + "/").status_code == 404
