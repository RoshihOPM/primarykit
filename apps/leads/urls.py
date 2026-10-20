from rest_framework.routers import SimpleRouter

from .views import LeadViewSet

router = SimpleRouter()
router.register("", LeadViewSet, basename="leads")
urlpatterns = router.urls
