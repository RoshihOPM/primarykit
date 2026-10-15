from django.conf import settings
from django.contrib.auth import update_session_auth_hash
from django.utils.translation import gettext_lazy as _
from rest_framework import generics, mixins, status, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .models import User
from .permissions import IsActiveSuperuser
from .serializers import (
    AdminUserUpdateSerializer,
    ChangePasswordSerializer,
    EmailTokenObtainPairSerializer,
    LogoutSerializer,
    RegisterSerializer,
    UserProfileUpdateSerializer,
    UserReadSerializer,
)
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
        return super().initial(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserReadSerializer(user).data, status=status.HTTP_201_CREATED)


class LoginView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer
    throttle_classes = [AccountRateThrottle]
    throttle_scope = "account_login"


class RefreshView(TokenRefreshView):
    throttle_classes = [AccountRateThrottle]
    throttle_scope = "account_refresh"


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [AccountRateThrottle]
    throttle_scope = "account_refresh"

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            refresh = RefreshToken(serializer.validated_data["refresh"])
            if str(refresh["user_id"]) != str(request.user.pk):
                raise ValidationError({"refresh": _("Invalid refresh token.")})
            refresh.blacklist()
        except (TokenError, KeyError) as exc:
            raise ValidationError({"refresh": _("Invalid refresh token.")}) from exc
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


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [AccountRateThrottle]
    throttle_scope = "account_password"

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
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
