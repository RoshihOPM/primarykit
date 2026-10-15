from django.urls import include, path
from rest_framework.routers import SimpleRouter

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
    path("users/me/", MeView.as_view(), name="users-me"),
    path("users/me/change-password/", ChangePasswordView.as_view(), name="users-change-password"),
    path("", include(router.urls)),
]
