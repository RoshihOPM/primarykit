from rest_framework.routers import SimpleRouter

from .views import DealCardLinkViewSet

router = SimpleRouter()
router.register("links", DealCardLinkViewSet, basename="crm-pipeline-links")
urlpatterns = router.urls
