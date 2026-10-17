from rest_framework.routers import SimpleRouter

from .views import DialogueViewSet

router = SimpleRouter()
router.register("chats", DialogueViewSet, basename="chat")
urlpatterns = router.urls
