"""Explicitly opt-in mail flows; generic responses for account discovery endpoints."""

import logging

from django.conf import settings
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.notifications.services import NotificationDeliveryError

from .email_serializers import (
    EmailRequestSerializer,
    PasswordResetConfirmSerializer,
    VerifyEmailSerializer,
)
from .email_services import send_password_reset_email, send_verification_email
from .models import User
from .throttles import AccountRateThrottle

logger = logging.getLogger(__name__)


class EmailFlowUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Email workflows are not configured for this project."
    default_code = "email_unavailable"


class EmailFlowView(APIView):
    permission_classes = (AllowAny,)
    authentication_classes = ()
    throttle_classes = (AccountRateThrottle,)
    throttle_scope = "account_email_request"

    def initial(self, request, *args, **kwargs):
        if not settings.AUTH_EMAIL_FLOWS_ENABLED:
            raise EmailFlowUnavailable()
        return super().initial(request, *args, **kwargs)


class ResendVerificationView(EmailFlowView):
    def post(self, request):
        serializer = EmailRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = User.objects.normalize_identity(serializer.validated_data["email"])
        user = User.objects.filter(email=email, is_active=True, email_verified=False).first()
        if user:
            try:
                send_verification_email(user)
            except NotificationDeliveryError:
                logger.error("Verification email request could not be fulfilled")
        return Response({"detail": "If eligible, an email will be sent."}, status=202)


class VerifyEmailView(EmailFlowView):
    throttle_scope = "account_email_confirm"

    def post(self, request):
        serializer = VerifyEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=204)


class PasswordResetRequestView(EmailFlowView):
    def post(self, request):
        serializer = EmailRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = User.objects.normalize_identity(serializer.validated_data["email"])
        user = User.objects.filter(email=email, is_active=True).first()
        if user:
            try:
                send_password_reset_email(user)
            except NotificationDeliveryError:
                logger.error("Password reset email request could not be fulfilled")
        return Response({"detail": "If eligible, an email will be sent."}, status=202)


class PasswordResetConfirmView(EmailFlowView):
    throttle_scope = "account_email_confirm"

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=204)
