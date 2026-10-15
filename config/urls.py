from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", include("apps.core.urls")),
    path("api/v1/", include("apps.users.urls")),
    path("api/v1/admin/rbac/", include("apps.rbac.urls")),
    path("api/v1/admin/audit/", include("apps.audit.urls")),
    path("api/v1/", include("apps.storage.urls")),
    path("api/v1/catalog/", include("apps.catalog.urls")),
]

if settings.DEBUG:
    urlpatterns += [
        path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
        path(
            "api/docs/",
            SpectacularSwaggerView.as_view(url_name="schema"),
            name="swagger-ui",
        ),
        path(
            "api/redoc/",
            SpectacularRedocView.as_view(url_name="schema"),
            name="redoc",
        ),
    ]
