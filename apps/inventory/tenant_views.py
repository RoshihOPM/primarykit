"""Tenant-scoped inventory API. No global list or detail endpoints."""

from django.db import transaction
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import SAFE_METHODS
from rest_framework.response import Response

from apps.core.audit import record_audit_event
from apps.organizations.policy import FULL_ACCESS, WRITERS, TenantPolicy

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
        if request.method not in SAFE_METHODS:
            self.get_policy().require_write()

    def lock_and_check_writer(self):
        policy = TenantPolicy.resolve(
            user=self.request.user, organization_id=self.kwargs["org_id"], lock=True
        )
        policy.require_write()
        return policy.organization

    def get_policy(self):
        if not hasattr(self, "_tenant_policy"):
            self._tenant_policy = TenantPolicy.resolve(
                user=self.request.user, organization_id=self.kwargs["org_id"]
            )
        return self._tenant_policy

    def get_scope(self):
        policy = self.get_policy()
        return policy.organization, policy.membership

    def get_accessible_warehouses(self):
        policy = self.get_policy()
        qs = policy.scope_queryset(
            Warehouse.objects.all(),
            organization_field="organization",
            branch_field="branch",
            active_branches=not policy.has_full_access,
        )
        if not policy.has_full_access:
            qs = qs.filter(is_active=True)
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
        self.get_policy().require_write()
        serializer = StockCommandSerializer(data=request.data, context={"view": self})
        serializer.is_valid(raise_exception=True)
        result = execute_stock_operation(
            actor=request.user, organization=organization, data=serializer.validated_data
        )
        return Response(result, status=status.HTTP_200_OK)
