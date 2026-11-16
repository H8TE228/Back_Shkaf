from rest_framework import serializers

from items.models import Item
from shkaf.serializers import coordinates_to_point

from .models import Notification, Subscription

MAX_SUBSCRIPTIONS = 20
MAX_RADIUS_KM = 50


class SubscriptionSerializer(serializers.ModelSerializer):
    exchange_format = serializers.ChoiceField(
        choices=Item.ExchangeFormat.choices, required=False, allow_blank=True
    )
    latitude = serializers.FloatField(source='center.y', required=False, allow_null=True, min_value=-90, max_value=90)
    longitude = serializers.FloatField(source='center.x', required=False, allow_null=True, min_value=-180, max_value=180)
    radius_km = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=MAX_RADIUS_KM)

    class Meta:
        model = Subscription
        fields = ('id', 'item_type', 'exchange_format', 'query', 'latitude', 'longitude', 'radius_km', 'is_active',
                  'created_at')
        read_only_fields = ('id', 'created_at')

    def validate(self, attrs):
        attrs = coordinates_to_point(attrs, 'center')
        center = attrs.get('center', getattr(self.instance, 'center', None))
        radius = attrs.get('radius_km', getattr(self.instance, 'radius_km', None))
        if (center is None) != (radius is None):
            raise serializers.ValidationError('Point and radius_km must be set together.')
        if self.instance is None:
            user = self.context['request'].user
            if user.subscriptions.count() >= MAX_SUBSCRIPTIONS:
                raise serializers.ValidationError(f'At most {MAX_SUBSCRIPTIONS} subscriptions are allowed.')
        return attrs


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ('id', 'type', 'payload', 'read_at', 'created_at')
        read_only_fields = fields
