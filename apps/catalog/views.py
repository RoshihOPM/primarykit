from django.db import transaction
from rest_framework import mixins, viewsets

from apps.core.audit import record_audit_event

from .models import AttributeDefinition, CatalogItem, Category
from .permissions import CatalogAccess
from .serializers import AttributeDefinitionSerializer, CatalogItemSerializer, CategorySerializer


class AuditedCatalogViewSet(viewsets.ModelViewSet):
    permission_classes = (CatalogAccess,)
    http_method_names = ("get", "post", "patch", "head", "options")
    audit_target_type = ""

    @transaction.atomic
    def perform_create(self, serializer):
        obj = serializer.save()
        record_audit_event(
            actor=self.request.user,
            action="catalog.object.created",
            target_type=self.audit_target_type,
            target_id=obj.pk,
        )

    @transaction.atomic
    def perform_update(self, serializer):
        obj = serializer.save()
        record_audit_event(
            actor=self.request.user,
            action="catalog.object.updated",
            target_type=self.audit_target_type,
            target_id=obj.pk,
        )


class CategoryViewSet(AuditedCatalogViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    audit_target_type = "catalog.Category"

    def get_queryset(self):
        queryset = super().get_queryset()
        if not self.request.user.is_superuser:
            queryset = queryset.filter(is_active=True)
        return queryset


class CatalogItemViewSet(AuditedCatalogViewSet):
    queryset = CatalogItem.objects.select_related("category").all()
    serializer_class = CatalogItemSerializer
    audit_target_type = "catalog.CatalogItem"

    def get_queryset(self):
        queryset = super().get_queryset()
        if not self.request.user.is_superuser:
            queryset = queryset.filter(is_active=True, category__is_active=True)
        category = self.request.query_params.get("category")
        if category:
            queryset = queryset.filter(category__slug=category)
        sku = self.request.query_params.get("sku")
        if sku:
            queryset = queryset.filter(sku__iexact=sku)
        return queryset


class AttributeDefinitionViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = (CatalogAccess,)
    serializer_class = AttributeDefinitionSerializer
    queryset = AttributeDefinition.objects.select_related("category").all()
    http_method_names = ("get", "post", "head", "options")

    def get_queryset(self):
        queryset = super().get_queryset()
        if not self.request.user.is_superuser:
            queryset = queryset.filter(category__is_active=True)
        category = self.request.query_params.get("category")
        if category:
            queryset = queryset.filter(category__slug=category)
        return queryset

    @transaction.atomic
    def perform_create(self, serializer):
        item = serializer.save()
        record_audit_event(
            actor=self.request.user,
            action="catalog.attribute.created",
            target_type="catalog.AttributeDefinition",
            target_id=item.pk,
        )
