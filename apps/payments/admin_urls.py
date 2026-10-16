from django.urls import path

from .admin_views import ManualReconciliationView

urlpatterns = [
    path(
        "<uuid:payment_id>/reconcile/",
        ManualReconciliationView.as_view(),
        name="payments-admin-reconcile",
    ),
]
