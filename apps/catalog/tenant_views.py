"""No unscoped catalog endpoints: every queryset is filtered by an active membership."""

from django.db import transaction
from rest_framework import mixins, viewsets
from rest_framework.permissions import SAFE_METHODS

from apps.core.audit import record_audit_event
from apps.organizations.policy import TenantPolicy

from .models import AttributeDefinition, CatalogItem, Category
from .permissions import CatalogAccess
from .serializers import AttributeDefinitionSerializer, CatalogItemSerializer, CategorySerializer


class CatalogScopeMixin:
    permission_classes = (CatalogAccess,)

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.get_scope()
        if request.method not in SAFE_METHODS:
            self.check_write_role()

    def get_policy(self):
        if not hasattr(self, "_tenant_policy"):
            self._tenant_policy = TenantPolicy.resolve(
                user=self.request.user, organization_id=self.kwargs["org_id"]
            )
        return self._tenant_policy

    def get_scope(self):
        policy = self.get_policy()
        return policy.organization, policy.membership

    def check_write_role(self):
        self.get_policy().require_write()

    def lock_and_check_writer(self):
        policy = TenantPolicy.resolve(
            user=self.request.user, organization_id=self.kwargs["org_id"], lock=True
        )
        policy.require_write()
        return policy.organization


class AuditedCatalogViewSet(CatalogScopeMixin, viewsets.ModelViewSet):
    http_method_names = ("get", "post", "patch", "head", "options")
    audit_target_type = ""

    @transaction.atomic
    def perform_create(self, serializer):
        org = self.lock_and_check_writer()
        obj = serializer.save(organization=org)
        record_audit_event(
            actor=self.request.user,
            action="catalog.object.created",
            target_type=self.audit_target_type,
            target_id=obj.pk,
            changes={"organization_id": str(org.pk)},
        )

    @transaction.atomic
    def perform_update(self, serializer):
        self.lock_and_check_writer()
        obj = serializer.save()
        record_audit_event(
            actor=self.request.user,
            action="catalog.object.updated",
            target_type=self.audit_target_type,
            target_id=obj.pk,
            changes={"organization_id": str(self.get_scope()[0].pk)},
        )


class CategoryViewSet(AuditedCatalogViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    audit_target_type = "catalog.Category"

    def get_queryset(self):
        _, membership = self.get_scope()
        queryset = self.get_policy().scope_queryset(
            super().get_queryset(), organization_field="organization"
        )
        if membership.role == "member":
            queryset = queryset.filter(is_active=True)
        return queryset


class CatalogItemViewSet(AuditedCatalogViewSet):
    queryset = CatalogItem.objects.select_related("category").all()
    serializer_class = CatalogItemSerializer
    audit_target_type = "catalog.CatalogItem"

    def get_queryset(self):
        _, membership = self.get_scope()
        queryset = self.get_policy().scope_queryset(
            super().get_queryset(), organization_field="organization"
        )
        if membership.role == "member":
            queryset = queryset.filter(is_active=True, category__is_active=True)
        category = self.request.query_params.get("category")
        if category:
            queryset = queryset.filter(category__slug=category)
        sku = self.request.query_params.get("sku")
        if sku:
            queryset = queryset.filter(sku__iexact=sku)
        return queryset


class AttributeDefinitionViewSet(
    CatalogScopeMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = AttributeDefinitionSerializer
    queryset = AttributeDefinition.objects.select_related("category").all()
    http_method_names = ("get", "post", "head", "options")

    def get_queryset(self):
        _, membership = self.get_scope()
        queryset = self.get_policy().scope_queryset(
            super().get_queryset(), organization_field="category__organization"
        )
        if membership.role == "member":
            queryset = queryset.filter(category__is_active=True)
        category = self.request.query_params.get("category")
        if category:
            queryset = queryset.filter(category__slug=category)
        return queryset

    @transaction.atomic
    def perform_create(self, serializer):
        self.lock_and_check_writer()
        obj = serializer.save()
        record_audit_event(
            actor=self.request.user,
            action="catalog.attribute.created",
            target_type="catalog.AttributeDefinition",
            target_id=obj.pk,
            changes={"organization_id": str(self.get_scope()[0].pk)},
        )
