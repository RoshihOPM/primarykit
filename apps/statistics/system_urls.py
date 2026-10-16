from django.urls import path

from .views import AvailableSystemStatisticsView, SystemStatisticsView

urlpatterns = [
    path("", SystemStatisticsView.as_view(), name="statistics-system-metrics"),
    path(
        "available/",
        AvailableSystemStatisticsView.as_view(),
        name="statistics-system-available",
    ),
]
