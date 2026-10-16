"""Read-only metrics API: personal, company owner/admin, and global superuser."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import build_context, metric_definitions, metric_results, period_response


class StatisticsView(APIView):
    permission_classes = (IsAuthenticated,)
    scope = "personal"

    def context(self, request, **kwargs):
        scope = "tenant" if "org_id" in kwargs else self.scope
        return build_context(
            actor=request.user,
            scope=scope,
            org_id=kwargs.get("org_id"),
            params=request.query_params,
        )

    def get(self, request, **kwargs):
        context = self.context(request, **kwargs)
        return Response(
            {
                "scope": context.scope,
                "period": period_response(context),
                "metrics": metric_results(context),
            }
        )


class AvailableStatisticsView(StatisticsView):
    def get(self, request, **kwargs):
        context = self.context(request, **kwargs)
        return Response(
            {
                "scope": context.scope,
                "metrics": metric_definitions(context),
            }
        )


class SystemStatisticsView(StatisticsView):
    scope = "system"


class AvailableSystemStatisticsView(AvailableStatisticsView):
    scope = "system"
