from rest_framework import mixins, status, viewsets
from rest_framework.response import Response

from apps.users.permissions import IsActiveSuperuser

from .models import InventoryOperation, StockBalance, StockReservation, Warehouse
from .serializers import (
    BalanceSerializer,
    InventoryOperationSerializer,
    ReservationSerializer,
    StockCommandSerializer,
    WarehouseSerializer,
)
from .services import execute_stock_operation


class WarehouseViewSet(viewsets.ModelViewSet):
    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer
    permission_classes = (IsActiveSuperuser,)
    http_method_names = ("get", "post", "patch", "head", "options")


class BalanceViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = StockBalance.objects.select_related("warehouse", "item").all()
    serializer_class = BalanceSerializer
    permission_classes = (IsActiveSuperuser,)


class ReservationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = StockReservation.objects.select_related("balance").all()
    serializer_class = ReservationSerializer
    permission_classes = (IsActiveSuperuser,)


class OperationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    queryset = InventoryOperation.objects.all()
    serializer_class = InventoryOperationSerializer
    permission_classes = (IsActiveSuperuser,)
    http_method_names = ("get", "post", "head", "options")

    def create(self, request):
        serializer = StockCommandSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = execute_stock_operation(actor=request.user, data=serializer.validated_data)
        return Response(result, status=status.HTTP_200_OK)
