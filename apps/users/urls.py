from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .email_views import (
    PasswordResetConfirmView,
    PasswordResetRequestView,
    ResendVerificationView,
    VerifyEmailView,
)
from .views import (
    AdminUserViewSet,
    ChangePasswordView,
    LoginView,
    LogoutView,
    MeView,
    RefreshView,
    RegistrationView,
)

router = SimpleRouter()
router.register("admin/users", AdminUserViewSet, basename="admin-users")

urlpatterns = [
    path("auth/register/", RegistrationView.as_view(), name="auth-register"),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/refresh/", RefreshView.as_view(), name="auth-refresh"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("auth/email/verify/", VerifyEmailView.as_view(), name="auth-email-verify"),
    path("auth/email/resend/", ResendVerificationView.as_view(), name="auth-email-resend"),
    path("auth/password/reset/request/", PasswordResetRequestView.as_view(), name="auth-password-reset-request"),
    path("auth/password/reset/confirm/", PasswordResetConfirmView.as_view(), name="auth-password-reset-confirm"),
    path("users/me/", MeView.as_view(), name="users-me"),
    path("users/me/change-password/", ChangePasswordView.as_view(), name="users-change-password"),
    path("", include(router.urls)),
]
