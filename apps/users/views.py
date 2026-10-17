from django.conf import settings
from django.contrib.auth import update_session_auth_hash
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import generics, mixins, status, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken, UntypedToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.core.audit import record_audit_event
from apps.notifications.services import NotificationDeliveryError

from .email_views import EmailFlowUnavailable
from .models import DeviceSession, User
from .permissions import IsActiveSuperuser
from .serializers import (
    AdminUserUpdateSerializer,
    ChangePasswordSerializer,
    DeviceSessionReadSerializer,
    EmailTokenObtainPairSerializer,
    LogoutSerializer,
    PasswordBoundTokenRefreshSerializer,
    RegisterSerializer,
    UserProfileUpdateSerializer,
    UserReadSerializer,
)
from .sessions import locked_session, revoke_all, revoke_on_password_change, revoke_one
from .throttles import AccountRateThrottle


class RegistrationView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AccountRateThrottle]
    throttle_scope = "account_registration"

    def initial(self, request, *args, **kwargs):
        if not settings.ALLOW_PUBLIC_REGISTRATION:
            raise PermissionDenied(_("Public registration is disabled."))
        if not settings.AUTH_EMAIL_FLOWS_ENABLED:
            raise EmailFlowUnavailable()
        return super().initial(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = serializer.save()
        except NotificationDeliveryError as exc:
            raise EmailFlowUnavailable() from exc
        return Response(UserReadSerializer(user).data, status=status.HTTP_201_CREATED)


class LoginView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer
    throttle_classes = [AccountRateThrottle]
    throttle_scope = "account_login"


class RefreshView(TokenRefreshView):
    serializer_class = PasswordBoundTokenRefreshSerializer
    throttle_classes = [AccountRateThrottle]
    throttle_scope = "account_refresh"


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [AccountRateThrottle]
    throttle_scope = "account_refresh"

    @transaction.atomic
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            # Same lock order as login/refresh/password-change/revoke-all.
            owner = User.objects.select_for_update().get(pk=request.user.pk)
            raw_refresh = serializer.validated_data["refresh"]
            # A concurrent rotation may already blacklist this signed refresh.
            # Still revoke its session instead of leaving a live device behind.
            refresh = UntypedToken(raw_refresh)
            if refresh["token_type"] != "refresh" or str(refresh["user_id"]) != str(owner.pk):
                raise ValidationError({"refresh": _("Invalid refresh token.")})
            session = locked_session(user=owner, refresh=refresh)
            try:
                RefreshToken(raw_refresh).blacklist()
            except TokenError:
                # Already blacklisted, but a valid signed refresh identifies the session.
                pass
            session.revoked_at = timezone.now()
            session.save(update_fields=["revoked_at"])
        except (InvalidToken, TokenError, KeyError, ValueError) as exc:
            raise ValidationError({"refresh": _("Invalid refresh token.")}) from exc
        return Response(status=status.HTTP_204_NO_CONTENT)


class DeviceSessionListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = DeviceSessionReadSerializer

    def get_queryset(self):
        return DeviceSession.objects.filter(
            user=self.request.user,
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).order_by("-created_at")


class DeviceSessionRevokeView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, session_id):
        revoke_one(user=request.user, session_id=session_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DeviceSessionRevokeAllView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        revoke_all(user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return self.request.user

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return UserProfileUpdateSerializer
        return UserReadSerializer

    @transaction.atomic
    def perform_update(self, serializer):
        old = {field: getattr(serializer.instance, field) for field in ("first_name", "last_name")}
        user = serializer.save()
        changed = {
            field: {"before": old[field], "after": getattr(user, field)}
            for field in old
            if old[field] != getattr(user, field)
        }
        if changed:
            record_audit_event(
                actor=user,
                action="users.profile.updated",
                target_type="users.User",
                target_id=user.pk,
                changes=changed,
            )


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [AccountRateThrottle]
    throttle_scope = "account_password"

    @transaction.atomic
    def post(self, request):
        user = User.objects.select_for_update().get(pk=request.user.pk)
        serializer = ChangePasswordSerializer(
            data=request.data, context={"request": request, "user": user}
        )
        serializer.is_valid(raise_exception=True)
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        revoke_on_password_change(user=user)
        record_audit_event(
            actor=user,
            action="users.password.changed",
            target_type="users.User",
            target_id=user.pk,
        )
        # Keeps a legitimate existing Django admin session alive.
        if request.auth is None:
            update_session_auth_hash(request, user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminUserViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = User.objects.all().order_by("-date_joined")
    permission_classes = [IsActiveSuperuser]
    http_method_names = ["get", "patch", "head", "options"]

    def get_serializer_class(self):
        if self.action == "partial_update":
            return AdminUserUpdateSerializer
        return UserReadSerializer

    @transaction.atomic
    def perform_update(self, serializer):
        fields = ("first_name", "last_name", "is_active")
        previous = {field: getattr(serializer.instance, field) for field in fields}
        user = serializer.save()
        changes = {
            field: {"before": previous[field], "after": getattr(user, field)}
            for field in fields
            if previous[field] != getattr(user, field)
        }
        if changes:
            record_audit_event(
                actor=self.request.user,
                action="users.admin.updated",
                target_type="users.User",
                target_id=user.pk,
                changes=changes,
            )
