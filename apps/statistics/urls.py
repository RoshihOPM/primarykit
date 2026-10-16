from django.urls import path

from .views import AvailableStatisticsView, StatisticsView

urlpatterns = [
    path("", StatisticsView.as_view(), name="statistics-metrics"),
    path("available/", AvailableStatisticsView.as_view(), name="statistics-available"),
]
