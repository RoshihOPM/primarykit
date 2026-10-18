from rest_framework.routers import SimpleRouter

from .views import FavoriteViewSet, SavedSearchViewSet

router = SimpleRouter()
router.register("favorites", FavoriteViewSet, basename="favorites")
router.register("saved-searches", SavedSearchViewSet, basename="saved-searches")
urlpatterns = router.urls
