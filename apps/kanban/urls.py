from rest_framework.routers import SimpleRouter

from .views import BoardViewSet, CardViewSet, ColumnViewSet

router = SimpleRouter()
router.register("boards", BoardViewSet, basename="kanban-boards")
router.register("columns", ColumnViewSet, basename="kanban-columns")
router.register("cards", CardViewSet, basename="kanban-cards")
urlpatterns = router.urls
