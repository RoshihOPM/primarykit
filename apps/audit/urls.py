from rest_framework.routers import SimpleRouter

from .views import AuditEventViewSet

router = SimpleRouter()
router.register("events", AuditEventViewSet, basename="audit-events")
urlpatterns = router.urls
