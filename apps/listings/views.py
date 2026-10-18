"""Public moderated ads plus private owner commands. Never expose private drafts."""

from django.db.models import Q
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import Listing, ListingCategory
from .serializers import (
    CreateListingSerializer,
    EditListingSerializer,
    ListingCategorySerializer,
    ListingSerializer,
    ModerateSerializer,
    VersionSerializer,
)
from .services import create_listing, edit_listing, transition_listing


class ListingViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = ListingSerializer
    http_method_names = ("get", "post", "patch", "head", "options")

    def get_permissions(self):
        if self.action in {"list", "retrieve", "categories"}:
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_queryset(self):
        qs = Listing.objects.select_related("category", "owner")
        user = self.request.user
        if self.action == "mine":
            return qs.filter(owner=user)
        if self.action == "pending":
            if not user.has_perm("listings.moderate_listing"):
                raise PermissionDenied()
            return qs.filter(status=Listing.Status.PENDING)
        if self.action == "retrieve":
            if user.is_authenticated:
                return qs.filter(
                    Q(
                        status=Listing.Status.PUBLISHED,
                        owner__is_active=True,
                        owner__email_verified=True,
                    )
                    | Q(owner=user)
                )
            return qs.filter(
                status=Listing.Status.PUBLISHED,
                owner__is_active=True,
                owner__email_verified=True,
            )
        return qs.filter(
            status=Listing.Status.PUBLISHED,
            owner__is_active=True,
            owner__email_verified=True,
        )

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        if category := request.query_params.get("category"):
            if len(category) > 80:
                raise ValidationError({"category": "Invalid category."})
            qs = qs.filter(category__slug=category)
        if term := request.query_params.get("q"):
            if len(term) > 80:
                raise ValidationError({"q": "Search is limited to 80 characters."})
            qs = qs.filter(title__icontains=term.strip())
        if location := request.query_params.get("location"):
            if len(location) > 120:
                raise ValidationError({"location": "Invalid location."})
            qs = qs.filter(location_label__icontains=location.strip())
        for param, suffix in (("min_price", "gte"), ("max_price", "lte")):
            if param in request.query_params:
                try:
                    value = int(request.query_params[param])
                except (TypeError, ValueError) as exc:
                    raise ValidationError({param: "Must be an integer."}) from exc
                if value < 0 or value > 10**15:
                    raise ValidationError({param: "Outside allowed range."})
                qs = qs.filter(**{f"price_minor__{suffix}": value})
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        return Response(self.get_serializer(qs, many=True).data)

    def create(self, request, *args, **kwargs):
        data = CreateListingSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        listing = create_listing(actor=request.user, fields=data.validated_data)
        return Response(self.get_serializer(listing).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        data = EditListingSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        changes = dict(data.validated_data)
        expected_version = changes.pop("expected_version")
        listing = edit_listing(
            actor=request.user,
            listing_id=kwargs["pk"],
            expected_version=expected_version,
            changes=changes,
        )
        return Response(self.get_serializer(listing).data)

    @action(detail=False, methods=["get"])
    def categories(self, request):
        qs = ListingCategory.objects.filter(active=True)
        return Response(ListingCategorySerializer(qs, many=True).data)

    @action(detail=False, methods=["get"])
    def mine(self, request):
        qs = self.get_queryset()
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        return Response(self.get_serializer(qs, many=True).data)

    @action(detail=False, methods=["get"])
    def pending(self, request):
        qs = self.get_queryset()
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        return Response(self.get_serializer(qs, many=True).data)

    def _transition(self, request, pk, action):
        data = VersionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        listing = transition_listing(
            actor=request.user,
            listing_id=pk,
            expected_version=data.validated_data["expected_version"],
            action=action,
        )
        return Response(self.get_serializer(listing).data)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        return self._transition(request, pk, "submit")

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        return self._transition(request, pk, "archive")

    @action(detail=True, methods=["post"], url_path="mark-sold")
    def mark_sold(self, request, pk=None):
        return self._transition(request, pk, "mark_sold")

    @action(detail=True, methods=["post"])
    def moderate(self, request, pk=None):
        data = ModerateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        listing = transition_listing(
            actor=request.user,
            listing_id=pk,
            expected_version=data.validated_data["expected_version"],
            action=data.validated_data["decision"],
        )
        return Response(self.get_serializer(listing).data)
