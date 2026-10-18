from rest_framework import serializers

from .models import Board, Card, Column


class BoardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Board
        fields = ("id", "name", "created_at")
        read_only_fields = ("id", "created_at")


class ColumnSerializer(serializers.ModelSerializer):
    class Meta:
        model = Column
        fields = ("id", "board", "name", "position")
        read_only_fields = ("id",)


class CardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Card
        fields = ("id", "board", "column", "title", "description", "position", "version")
        read_only_fields = ("id", "version")


class MoveSerializer(serializers.Serializer):
    target_column_id = serializers.UUIDField()
    expected_version = serializers.IntegerField(min_value=0)
