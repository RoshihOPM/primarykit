from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Order
from .serializers import OrderSerializer, PlaceOrderSerializer
from .services import cancel_order, place_order


class OrderViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = (IsAuthenticated,)
    serializer_class = OrderSerializer
    http_method_names = ("get", "post", "head", "options")

    def get_queryset(self):
        return Order.objects.filter(owner=self.request.user).prefetch_related("items")

    def create(self, request, *args, **kwargs):
        serializer = PlaceOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = place_order(
            actor=request.user,
            currency=serializer.validated_data["currency"],
            lines=serializer.validated_data["lines"],
            idempotency_key=serializer.validated_data["idempotency_key"],
        )
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        order = cancel_order(actor=request.user, order_id=pk)
        return Response(OrderSerializer(order).data)
