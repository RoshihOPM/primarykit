"""Root URL configuration; copied apps self-register through manifest.py."""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from apps.core.module_registry import module_routes

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", include("apps.core.urls")),
]
urlpatterns += [path(prefix, include(module_urls)) for prefix, module_urls in module_routes()]

if settings.DEBUG:
    urlpatterns += [
        path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
        path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
        path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    ]
