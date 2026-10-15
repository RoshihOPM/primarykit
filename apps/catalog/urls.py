from rest_framework.routers import SimpleRouter

from .views import AttributeDefinitionViewSet, CatalogItemViewSet, CategoryViewSet

router = SimpleRouter()
router.register("categories", CategoryViewSet, basename="catalog-categories")
router.register("attributes", AttributeDefinitionViewSet, basename="catalog-attributes")
router.register("items", CatalogItemViewSet, basename="catalog-items")
urlpatterns = router.urls
