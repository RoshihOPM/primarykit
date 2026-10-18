from rest_framework.routers import SimpleRouter

from .views import ContactViewSet

router = SimpleRouter()
router.register("", ContactViewSet, basename="contacts")
urlpatterns = router.urls
