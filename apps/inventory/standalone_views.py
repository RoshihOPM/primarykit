"""Standalone Inventory REST API with per-user scoping and no superuser IDOR bypass."""

from django.db import transaction
from rest_framework import mixins, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.audit import record_audit_event

from .models import InventoryItem, InventoryOperation, StockBalance, StockReservation, Warehouse
from .serializers import (
    BalanceSerializer,
    InventoryItemSerializer,
    InventoryOperationSerializer,
    ReservationSerializer,
    StockCommandSerializer,
    WarehouseSerializer,
)
from .services import execute_stock_operation


class OwnerInventoryViewSet(viewsets.ModelViewSet):
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
            action="inventory.object.created",
            target_type=self.audit_target_type,
            target_id=obj.pk,
        )

    @transaction.atomic
    def perform_update(self, serializer):
        obj = serializer.save()
        record_audit_event(
            actor=self.request.user,
            action="inventory.object.updated",
            target_type=self.audit_target_type,
            target_id=obj.pk,
        )


class InventoryItemViewSet(OwnerInventoryViewSet):
    queryset = InventoryItem.objects.all()
    serializer_class = InventoryItemSerializer
    audit_target_type = "inventory.InventoryItem"


class WarehouseViewSet(OwnerInventoryViewSet):
    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer
    audit_target_type = "inventory.Warehouse"


class BalanceViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = (IsAuthenticated,)
    serializer_class = BalanceSerializer

    def get_queryset(self):
        return StockBalance.objects.filter(owner=self.request.user).select_related(
            "warehouse", "item"
        ).order_by("pk")


class ReservationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = (IsAuthenticated,)
    serializer_class = ReservationSerializer

    def get_queryset(self):
        return StockReservation.objects.filter(balance__owner=self.request.user).select_related(
            "balance"
        ).order_by("pk")


class OperationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = (IsAuthenticated,)
    serializer_class = InventoryOperationSerializer
    http_method_names = ("get", "post", "head", "options")

    def get_queryset(self):
        return InventoryOperation.objects.filter(owner=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = StockCommandSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        result = execute_stock_operation(actor=request.user, data=serializer.validated_data)
        return Response(result, status=status.HTTP_200_OK)
