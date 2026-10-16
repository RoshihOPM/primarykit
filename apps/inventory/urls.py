from django.conf import settings
from rest_framework.routers import SimpleRouter

from .views import BalanceViewSet, OperationViewSet, ReservationViewSet, WarehouseViewSet

router = SimpleRouter()
if settings.INVENTORY_MODE == "standalone":
    from .standalone_views import InventoryItemViewSet

    router.register("items", InventoryItemViewSet, basename="inventory-items")
router.register("warehouses", WarehouseViewSet, basename="inventory-warehouses")
router.register("balances", BalanceViewSet, basename="inventory-balances")
router.register("reservations", ReservationViewSet, basename="inventory-reservations")
router.register("operations", OperationViewSet, basename="inventory-operations")
urlpatterns = router.urls
