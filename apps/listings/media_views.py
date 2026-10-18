"""Explicit media HTTP boundary: private objects are never exposed by URL."""

from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .media import (
    add_image,
    moderate_image,
    private_storage,
    remove_image,
    require_media,
    serialize_image,
    visible_images,
)
from .models import Listing


class UploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    expected_version = serializers.IntegerField(min_value=0)


class RemoveSerializer(serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=0)


class ImageModerationSerializer(RemoveSerializer):
    decision = serializers.ChoiceField(choices=("approve", "reject"))


def listing_or_404(listing_id):
    return get_object_or_404(Listing.objects.select_related("owner"), pk=listing_id)


class MediaCollection(APIView):
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request, listing_id):
        require_media()
        listing = listing_or_404(listing_id)
        return Response(
            [
                serialize_image(image)
                for image in visible_images(listing=listing, actor=request.user)
            ]
        )

    def post(self, request, listing_id):
        # Ownership checked again inside the locking service, not only at the API edge.
        if not request.user.is_authenticated:
            raise NotFound()
        data = UploadSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        image = add_image(
            actor=request.user,
            listing_id=listing_id,
            expected_version=data.validated_data["expected_version"],
            uploaded=data.validated_data["file"],
        )
        return Response(serialize_image(image), status=status.HTTP_201_CREATED)


class MediaDetail(APIView):
    permission_classes = [AllowAny]

    def get(self, request, listing_id, image_id):
        require_media()
        listing = listing_or_404(listing_id)
        visible = visible_images(listing=listing, actor=request.user)
        image = visible.filter(pk=image_id).first()
        if image is None:
            raise NotFound()
        # Never return a signed Storage URL or an S3 redirect. Streaming is
        # intentional: no-store gives immediate revocation on unpublish.
        obj = private_storage().open(image.private_key, "rb")
        response = FileResponse(obj, content_type="image/jpeg")
        response["Cache-Control"] = "no-store, max-age=0"
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Disposition"] = f'inline; filename="{image.pk}.jpg"'
        return response

    def delete(self, request, listing_id, image_id):
        if not request.user.is_authenticated:
            raise NotFound()
        data = RemoveSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        remove_image(
            actor=request.user,
            listing_id=listing_id,
            image_id=image_id,
            expected_version=data.validated_data["expected_version"],
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class MediaModeration(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, listing_id, image_id):
        data = ImageModerationSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        image = moderate_image(
            actor=request.user,
            listing_id=listing_id,
            image_id=image_id,
            expected_version=data.validated_data["expected_version"],
            decision=data.validated_data["decision"],
        )
        return Response(serialize_image(image))
