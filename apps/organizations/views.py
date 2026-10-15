"""All organization-scoped endpoints require membership and never trust client tenant IDs."""

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.audit import record_audit_event

from .models import Branch, BranchAccess, Invitation, Membership, Organization
from .permissions import get_active_membership, require_branch_access, require_org_role
from .serializers import (
    BranchAccessSerializer,
    BranchSerializer,
    InvitationCreateSerializer,
    InvitationSerializer,
    MemberRoleSerializer,
    MembershipSerializer,
    OrganizationSerializer,
    OrganizationUpdateSerializer,
)
from .services import (
    accept_invitation,
    create_invitation,
    create_organization,
    set_branch_access,
    update_membership,
)

ADMIN_ROLES = (Membership.Role.OWNER, Membership.Role.ADMIN)


class OrganizationListCreateView(generics.ListCreateAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = OrganizationSerializer

    def get_queryset(self):
        return Organization.objects.filter(
            is_active=True,
            memberships__user=self.request.user,
            memberships__is_active=True,
        ).distinct()

    def perform_create(self, serializer):
        # Serializer validates fields but the service atomically creates the owner.
        org = create_organization(
            actor=self.request.user,
            slug=serializer.validated_data["slug"],
            name=serializer.validated_data["name"],
        )
        serializer.instance = org


class OrganizationDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = OrganizationSerializer
    permission_classes = (IsAuthenticated,)
    http_method_names = ("get", "patch", "head", "options")

    def get_queryset(self):
        return Organization.objects.filter(
            is_active=True,
            memberships__user=self.request.user,
            memberships__is_active=True,
        )

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return OrganizationUpdateSerializer
        return OrganizationSerializer

    @transaction.atomic
    def perform_update(self, serializer):
        require_org_role(
            user=self.request.user, organization=serializer.instance, roles=ADMIN_ROLES
        )
        org = serializer.save()
        record_audit_event(
            actor=self.request.user,
            action="organizations.updated",
            target_type="organizations.Organization",
            target_id=org.pk,
        )


def organization_for(request, org_id):
    org = get_object_or_404(Organization, pk=org_id, is_active=True)
    return org, get_active_membership(user=request.user, organization=org)


class BranchListCreateView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, org_id):
        org, membership = organization_for(request, org_id)
        qs = Branch.objects.filter(organization=org, is_active=True)
        if membership.role not in ADMIN_ROLES:
            qs = qs.filter(member_access__membership=membership)
        return Response(BranchSerializer(qs.order_by("code"), many=True).data)

    @transaction.atomic
    def post(self, request, org_id):
        org, _ = organization_for(request, org_id)
        require_org_role(user=request.user, organization=org, roles=ADMIN_ROLES)
        serializer = BranchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        branch = serializer.save(organization=org)
        record_audit_event(
            actor=request.user,
            action="organizations.branch.created",
            target_type="organizations.Branch",
            target_id=branch.pk,
        )
        return Response(BranchSerializer(branch).data, status=201)


class BranchDetailView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, org_id, branch_id):
        org, _ = organization_for(request, org_id)
        branch = get_object_or_404(Branch, pk=branch_id, organization=org, is_active=True)
        require_branch_access(user=request.user, branch=branch)
        return Response(BranchSerializer(branch).data)

    @transaction.atomic
    def patch(self, request, org_id, branch_id):
        org, _ = organization_for(request, org_id)
        require_org_role(user=request.user, organization=org, roles=ADMIN_ROLES)
        branch = get_object_or_404(Branch, pk=branch_id, organization=org, is_active=True)
        serializer = BranchSerializer(branch, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        branch = serializer.save()
        record_audit_event(
            actor=request.user,
            action="organizations.branch.updated",
            target_type="organizations.Branch",
            target_id=branch.pk,
        )
        return Response(BranchSerializer(branch).data)


class MemberListView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, org_id):
        org, _ = organization_for(request, org_id)
        require_org_role(user=request.user, organization=org, roles=ADMIN_ROLES)
        members = Membership.objects.filter(organization=org, is_active=True).order_by("created_at")
        return Response(MembershipSerializer(members, many=True).data)


class MemberDetailView(APIView):
    permission_classes = (IsAuthenticated,)

    def patch(self, request, org_id, member_id):
        org, _ = organization_for(request, org_id)
        serializer = MemberRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        member = update_membership(
            actor=request.user,
            organization=org,
            membership_id=member_id,
            new_role=serializer.validated_data["role"],
        )
        return Response(MembershipSerializer(member).data)

    def delete(self, request, org_id, member_id):
        org, _ = organization_for(request, org_id)
        update_membership(
            actor=request.user, organization=org, membership_id=member_id, deactivate=True
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class BranchGrantsView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, org_id, member_id):
        org, _ = organization_for(request, org_id)
        require_org_role(user=request.user, organization=org, roles=ADMIN_ROLES)
        member = get_object_or_404(Membership, pk=member_id, organization=org, is_active=True)
        return Response(
            {
                "branch_ids": list(
                    BranchAccess.objects.filter(membership=member).values_list(
                        "branch_id", flat=True
                    )
                )
            }
        )

    def put(self, request, org_id, member_id):
        org, _ = organization_for(request, org_id)
        serializer = BranchAccessSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        set_branch_access(
            actor=request.user,
            organization=org,
            membership_id=member_id,
            branch_ids=serializer.validated_data["branch_ids"],
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class InvitationListCreateView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, org_id):
        org, _ = organization_for(request, org_id)
        require_org_role(user=request.user, organization=org, roles=ADMIN_ROLES)
        qs = Invitation.objects.filter(organization=org).order_by("-created_at")
        return Response(InvitationSerializer(qs, many=True).data)

    def post(self, request, org_id):
        org, _ = organization_for(request, org_id)
        serializer = InvitationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invite = create_invitation(
            actor=request.user, organization=org, **serializer.validated_data
        )
        return Response(InvitationSerializer(invite).data, status=201)


class MyInvitationsView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        invites = Invitation.objects.filter(
            invitee=request.user,
            state=Invitation.State.PENDING,
            expires_at__gt=timezone.now(),
            organization__is_active=True,
        ).select_related("organization")
        return Response(InvitationSerializer(invites, many=True).data)


class InvitationAcceptView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, invitation_id):
        member = accept_invitation(actor=request.user, invitation_id=invitation_id)
        return Response(MembershipSerializer(member).data, status=200)
