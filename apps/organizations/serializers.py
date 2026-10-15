from rest_framework import serializers

from apps.users.models import User

from .models import Branch, Invitation, Membership, Organization


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ("id", "slug", "name", "is_active")
        read_only_fields = ("id", "is_active")


class OrganizationUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ("name",)


class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ("id", "code", "name", "is_active")
        read_only_fields = ("id",)


class MembershipSerializer(serializers.ModelSerializer):
    class Meta:
        model = Membership
        fields = ("id", "user", "role", "is_active", "created_at")
        read_only_fields = fields


class MemberRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=Membership.Role.choices)


class BranchAccessSerializer(serializers.Serializer):
    branch_ids = serializers.ListField(
        child=serializers.UUIDField(), allow_empty=True
    )

    def validate_branch_ids(self, values):
        if len(values) != len(set(values)):
            raise serializers.ValidationError("Branch IDs must be unique.")
        return values


class InvitationCreateSerializer(serializers.Serializer):
    invitee = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
    role = serializers.ChoiceField(
        choices=[
            (Membership.Role.ADMIN, "Admin"),
            (Membership.Role.MANAGER, "Manager"),
            (Membership.Role.MEMBER, "Member"),
        ]
    )


class InvitationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invitation
        fields = ("id", "organization", "invitee", "role", "state", "expires_at")
        read_only_fields = fields
