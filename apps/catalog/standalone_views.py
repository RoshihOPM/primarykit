"""Personal Catalog API. No superuser override across users."""

from django.db import transaction
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from apps.core.audit import record_audit_event

from .models import AttributeDefinition, CatalogItem, Category
from .serializers import AttributeDefinitionSerializer, CatalogItemSerializer, CategorySerializer


class OwnerCatalogViewSet(viewsets.ModelViewSet):
    permission_classes = (IsAuthenticated,)
    http_method_names = ("get", "post", "patch", "head", "options")
    audit_target_type = ""

    def get_queryset(self):
        return super().get_queryset().filter(owner=self.request.user)

    @transaction.atomic
    def perform_create(self, serializer):
        obj = serializer.save(owner=self.request.user)
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


class CategoryViewSet(OwnerCatalogViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    audit_target_type = "catalog.Category"


class CatalogItemViewSet(OwnerCatalogViewSet):
    queryset = CatalogItem.objects.select_related("category").all()
    serializer_class = CatalogItemSerializer
    audit_target_type = "catalog.CatalogItem"

    def get_queryset(self):
        qs = super().get_queryset()
        if category := self.request.query_params.get("category"):
            qs = qs.filter(category__slug=category)
        if sku := self.request.query_params.get("sku"):
            qs = qs.filter(sku__iexact=sku)
        return qs


class AttributeDefinitionViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = (IsAuthenticated,)
    queryset = AttributeDefinition.objects.select_related("category").all()
    serializer_class = AttributeDefinitionSerializer
    http_method_names = ("get", "post", "head", "options")

    def get_queryset(self):
        qs = super().get_queryset().filter(category__owner=self.request.user)
        if category := self.request.query_params.get("category"):
            qs = qs.filter(category__slug=category)
        return qs

    @transaction.atomic
    def perform_create(self, serializer):
        obj = serializer.save()
        record_audit_event(
            actor=self.request.user,
            action="catalog.attribute.created",
            target_type="catalog.AttributeDefinition",
            target_id=obj.pk,
        )
