from rest_framework import serializers

from items.serializers import ItemBriefSerializer

from .models import Exchange


class ExchangeSerializer(serializers.ModelSerializer):
    item = ItemBriefSerializer(read_only=True)
    giver_id = serializers.IntegerField(read_only=True)
    receiver_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Exchange
        fields = (
            'id', 'item', 'giver_id', 'receiver_id', 'status', 'giver_confirmed_at',
            'receiver_confirmed_at', 'completed_at', 'created_at', 'updated_at',
        )
        read_only_fields = fields
