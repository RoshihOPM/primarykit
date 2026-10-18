from rest_framework.routers import SimpleRouter

from .views import ListingViewSet

router = SimpleRouter()
router.register("", ListingViewSet, basename="listings")
urlpatterns = router.urls
