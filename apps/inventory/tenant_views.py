"""Tenant-scoped inventory API. No global list or detail endpoints."""

from django.db import transaction
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import SAFE_METHODS
from rest_framework.response import Response

from apps.core.audit import record_audit_event
from apps.organizations.models import Organization
from apps.organizations.permissions import get_active_membership
from apps.organizations.scoping import (
    FULL_ACCESS,
    WRITERS,
    branch_ids_for,
    organization_scope,
    require_writer,
)

from .models import InventoryOperation, StockBalance, StockReservation, Warehouse
from .serializers import (
    BalanceSerializer,
    InventoryOperationSerializer,
    ReservationSerializer,
    StockCommandSerializer,
    WarehouseSerializer,
)
from .services import execute_stock_operation


class InventoryScopeMixin:
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        _, membership = self.get_scope()
        if request.method not in SAFE_METHODS:
            require_writer(membership)

    def lock_and_check_writer(self):
        org = Organization.objects.select_for_update().get(pk=self.get_scope()[0].pk)
        membership = get_active_membership(user=self.request.user, organization=org)
        require_writer(membership)
        return org

    def get_scope(self):
        if not hasattr(self, "_tenant_scope"):
            self._tenant_scope = organization_scope(
                user=self.request.user, org_id=self.kwargs["org_id"]
            )
        return self._tenant_scope

    def get_accessible_warehouses(self):
        organization, membership = self.get_scope()
        qs = Warehouse.objects.filter(organization=organization)
        if membership.role not in FULL_ACCESS:
            qs = qs.filter(
                is_active=True,
                branch__is_active=True,
                branch_id__in=branch_ids_for(membership),
            )
        return qs


class WarehouseViewSet(InventoryScopeMixin, viewsets.ModelViewSet):
    serializer_class = WarehouseSerializer
    queryset = Warehouse.objects.all()
    http_method_names = ("get", "post", "patch", "head", "options")

    def get_queryset(self):
        return self.get_accessible_warehouses()

    @transaction.atomic
    def perform_create(self, serializer):
        org = self.lock_and_check_writer()
        warehouse = serializer.save(organization=org)
        record_audit_event(
            actor=self.request.user,
            action="inventory.warehouse.created",
            target_type="inventory.Warehouse",
            target_id=warehouse.pk,
        )

    @transaction.atomic
    def perform_update(self, serializer):
        self.lock_and_check_writer()
        warehouse = serializer.save()
        record_audit_event(
            actor=self.request.user,
            action="inventory.warehouse.updated",
            target_type="inventory.Warehouse",
            target_id=warehouse.pk,
        )


class BalanceViewSet(
    InventoryScopeMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = BalanceSerializer

    def get_queryset(self):
        organization = self.get_scope()[0]
        return StockBalance.objects.filter(
            organization=organization,
            warehouse__in=self.get_accessible_warehouses(),
        ).select_related("warehouse", "item")


class ReservationViewSet(
    InventoryScopeMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ReservationSerializer

    def get_queryset(self):
        _, membership = self.get_scope()
        if membership.role not in WRITERS:
            raise PermissionDenied("Only inventory staff may read reservations.")
        return StockReservation.objects.filter(
            balance__organization=membership.organization,
            balance__warehouse__in=self.get_accessible_warehouses(),
        ).select_related("balance")


class OperationViewSet(
    InventoryScopeMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = InventoryOperationSerializer
    http_method_names = ("get", "post", "head", "options")

    def get_queryset(self):
        organization, membership = self.get_scope()
        if membership.role not in FULL_ACCESS:
            raise PermissionDenied("Operation history requires organization owner/admin.")
        return InventoryOperation.objects.filter(organization=organization)

    def create(self, request, *args, **kwargs):
        organization, membership = self.get_scope()
        require_writer(membership)
        serializer = StockCommandSerializer(data=request.data, context={"view": self})
        serializer.is_valid(raise_exception=True)
        result = execute_stock_operation(
            actor=request.user, organization=organization, data=serializer.validated_data
        )
        return Response(result, status=status.HTTP_200_OK)
