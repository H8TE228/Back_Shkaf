from rest_framework import serializers

from exchange_points.serializers import ExchangePointSerializer
from items.serializers import ItemSerializer

from .models import Bookmark


class BookmarkSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True, allow_null=True)
    point = ExchangePointSerializer(read_only=True, allow_null=True)

    class Meta:
        model = Bookmark
        fields = ('id', 'created_at', 'item', 'point')
        read_only_fields = fields
