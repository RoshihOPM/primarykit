from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Sale
from .serializers import RecordSaleSerializer, SaleSerializer
from .services import record_sale, void_sale


class SaleViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = (IsAuthenticated,)
    serializer_class = SaleSerializer
    http_method_names = ("get", "post", "head", "options")

    def get_queryset(self):
        return Sale.objects.filter(owner=self.request.user).prefetch_related("lines")

    def create(self, request, *args, **kwargs):
        serializer = RecordSaleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sale = record_sale(actor=request.user, **serializer.validated_data)
        return Response(SaleSerializer(sale).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        sale = void_sale(actor=request.user, sale_id=pk)
        return Response(SaleSerializer(sale).data)
