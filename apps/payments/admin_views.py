"""Manual test reconciliation; NEVER expose as a public payment webhook."""

from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import ManualReconciliationSerializer, PaymentSerializer
from .services import reconcile_manual


class ManualReconciliationView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, payment_id):
        if not request.user.is_superuser:
            raise PermissionDenied("Superuser access required.")
        serializer = ManualReconciliationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = reconcile_manual(
            actor=request.user, payment_id=payment_id, **serializer.validated_data
        )
        return Response(PaymentSerializer(payment).data)
