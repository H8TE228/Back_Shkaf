from rest_framework import serializers

from exchange_points.models import ExchangePoint
from users.models import User

from .models import InventoryRecord, PointMember, ShiftAssignment, VolunteerShift


class PointRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = PointMember
        fields = ('point', 'role')


class PointStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExchangePoint
        fields = ('id', 'status')
        extra_kwargs = {'status': {'required': True}}


class InventorySerializer(serializers.ModelSerializer):
    client = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(is_active=True, deleted_at__isnull=True),
                                                 required=False, allow_null=True)

    class Meta:
        model = InventoryRecord
        fields = ('id', 'item_type', 'direction', 'quantity', 'weight_kg', 'client', 'recorded_by', 'created_at')
        read_only_fields = ('recorded_by', 'created_at')


class ShiftSerializer(serializers.ModelSerializer):
    occupied = serializers.IntegerField(read_only=True)
    my_status = serializers.CharField(read_only=True, allow_null=True)

    class Meta:
        model = VolunteerShift
        fields = ('id', 'starts_at', 'ends_at', 'capacity', 'occupied', 'my_status')

    def validate(self, attrs):
        starts_at = attrs.get('starts_at', getattr(self.instance, 'starts_at', None))
        ends_at = attrs.get('ends_at', getattr(self.instance, 'ends_at', None))
        if starts_at is not None and ends_at is not None and ends_at <= starts_at:
            raise serializers.ValidationError({'ends_at': 'Must be after starts_at.'})
        return attrs


class AssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShiftAssignment
        fields = ('id', 'shift', 'user', 'status')
        read_only_fields = ('shift', 'user', 'status')
