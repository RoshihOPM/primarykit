from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import PaymentIntent
from .serializers import CreatePaymentSerializer, PaymentSerializer
from .services import cancel_intent, create_intent


class PaymentViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin,
    mixins.CreateModelMixin, viewsets.GenericViewSet,
):
    permission_classes = (IsAuthenticated,)
    serializer_class = PaymentSerializer
    http_method_names = ("get", "post", "head", "options")

    def get_queryset(self):
        return PaymentIntent.objects.filter(owner=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = CreatePaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = create_intent(actor=request.user, **serializer.validated_data)
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        payment = cancel_intent(actor=request.user, payment_id=pk)
        return Response(PaymentSerializer(payment).data)
