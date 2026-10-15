from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import PermissionViewSet, RoleViewSet, UserRolesView

router = SimpleRouter()
router.register("roles", RoleViewSet, basename="rbac-roles")
router.register("permissions", PermissionViewSet, basename="rbac-permissions")

urlpatterns = [
    path("users/<uuid:user_id>/roles/", UserRolesView.as_view(), name="rbac-user-roles"),
    *router.urls,
]
