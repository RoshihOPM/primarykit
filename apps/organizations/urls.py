from django.urls import path

from .views import (
    BranchDetailView,
    BranchGrantsView,
    BranchListCreateView,
    InvitationAcceptView,
    InvitationListCreateView,
    MemberDetailView,
    MemberListView,
    MyInvitationsView,
    OrganizationDetailView,
    OrganizationListCreateView,
)

urlpatterns = [
    path("organizations/", OrganizationListCreateView.as_view(), name="org-list"),
    path("organizations/<uuid:pk>/", OrganizationDetailView.as_view(), name="org-detail"),
    path("organizations/<uuid:org_id>/branches/", BranchListCreateView.as_view(), name="org-branches"),
    path(
        "organizations/<uuid:org_id>/branches/<uuid:branch_id>/",
        BranchDetailView.as_view(), name="org-branch-detail",
    ),
    path("organizations/<uuid:org_id>/members/", MemberListView.as_view(), name="org-members"),
    path(
        "organizations/<uuid:org_id>/members/<uuid:member_id>/",
        MemberDetailView.as_view(), name="org-member-detail",
    ),
    path(
        "organizations/<uuid:org_id>/members/<uuid:member_id>/branches/",
        BranchGrantsView.as_view(), name="org-member-branches",
    ),
    path(
        "organizations/<uuid:org_id>/invitations/",
        InvitationListCreateView.as_view(), name="org-invitations",
    ),
    path("invitations/mine/", MyInvitationsView.as_view(), name="org-my-invitations"),
    path(
        "invitations/<uuid:invitation_id>/accept/",
        InvitationAcceptView.as_view(), name="org-invitation-accept",
    ),
]
