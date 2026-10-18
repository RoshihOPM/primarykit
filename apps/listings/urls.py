from django.urls import path
from rest_framework.routers import SimpleRouter

from .media_views import MediaCollection, MediaDetail, MediaModeration
from .views import ListingViewSet

router = SimpleRouter()
router.register("", ListingViewSet, basename="listings")
urlpatterns = [
    path("<uuid:listing_id>/media/", MediaCollection.as_view(), name="listings-media-list"),
    path(
        "<uuid:listing_id>/media/<uuid:image_id>/",
        MediaDetail.as_view(),
        name="listings-media-detail",
    ),
    path(
        "<uuid:listing_id>/media/<uuid:image_id>/moderate/",
        MediaModeration.as_view(),
        name="listings-media-moderate",
    ),
] + router.urls
