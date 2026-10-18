from rest_framework.routers import SimpleRouter

from .views import DealViewSet

router = SimpleRouter()
router.register("", DealViewSet, basename="deals")
urlpatterns = router.urls
