import math
import re
from itertools import pairwise

from django.contrib.gis.geos import Point
from django.db import transaction
from rest_framework import serializers

from .models import Address, ExchangePoint


class AddressSerializer(serializers.ModelSerializer):
    latitude = serializers.FloatField(source='location.y', min_value=-90, max_value=90)
    longitude = serializers.FloatField(source='location.x', min_value=-180, max_value=180)

    class Meta:
        model = Address
        fields = ('country', 'region', 'city', 'district', 'street', 'building', 'postal_code',
                  'latitude', 'longitude')

    def validate(self, attrs):
        location = attrs.get('location')
        if location is not None:
            if set(location) != {'x', 'y'}:
                raise serializers.ValidationError('Both latitude and longitude are required.')
            if not all(math.isfinite(value) for value in location.values()):
                raise serializers.ValidationError('Coordinates must be finite numbers.')
            attrs['location'] = Point(location['x'], location['y'], srid=4326)
        return attrs


class OpeningIntervalSerializer(serializers.Serializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['from'] = serializers.RegexField(regex=r'^[0-9]{2}:[0-9]{2}$')
        self.fields['to'] = serializers.RegexField(regex=r'^[0-9]{2}:[0-9]{2}$')

    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError({key: 'Unknown field.' for key in sorted(unknown)})
        return super().to_internal_value(data)

    def validate(self, attrs):
        if set(attrs) != {'from', 'to'}:
            raise serializers.ValidationError('Both from and to are required.')
        minutes = []
        for name in ('from', 'to'):
            if not re.fullmatch(r'[0-9]{2}:[0-9]{2}', attrs[name]):
                raise serializers.ValidationError({name: 'Invalid time.'})
            hours, minute = map(int, attrs[name].split(':'))
            if minute > 59 or hours > 24 or (hours == 24 and (minute != 0 or name == 'from')):
                raise serializers.ValidationError({name: 'Invalid time.'})
            minutes.append(hours * 60 + minute)
        if minutes[0] >= minutes[1]:
            raise serializers.ValidationError('End time must be later than start time.')
        return attrs


class OpeningHoursSerializer(serializers.Serializer):
    mon = OpeningIntervalSerializer(many=True, required=False)
    tue = OpeningIntervalSerializer(many=True, required=False)
    wed = OpeningIntervalSerializer(many=True, required=False)
    thu = OpeningIntervalSerializer(many=True, required=False)
    fri = OpeningIntervalSerializer(many=True, required=False)
    sat = OpeningIntervalSerializer(many=True, required=False)
    sun = OpeningIntervalSerializer(many=True, required=False)

    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError({key: 'Unknown day.' for key in sorted(unknown)})
        return super().to_internal_value(data)

    def validate(self, attrs):
        for day, intervals in attrs.items():
            ordered = sorted(intervals, key=lambda interval: interval['from'])
            if any(previous['to'] > current['from'] for previous, current in pairwise(ordered)):
                raise serializers.ValidationError({day: 'Opening intervals must not overlap.'})
        return attrs


class ExchangePointSerializer(serializers.ModelSerializer):
    address = AddressSerializer()
    opening_hours = OpeningHoursSerializer(required=False)
    formats = serializers.ListField(
        child=serializers.ChoiceField(choices=ExchangePoint.Format.choices), required=False
    )

    class Meta:
        model = ExchangePoint
        fields = (
            'id', 'address', 'title', 'description', 'opening_hours', 'phone', 'email',
            'website', 'formats', 'status', 'verified_at', 'verified_by', 'picture',
            'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'verified_at', 'verified_by', 'picture', 'created_at', 'updated_at')

    def validate_formats(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError('Formats must not contain duplicates.')
        return value

    @transaction.atomic
    def create(self, validated_data):
        address_data = validated_data.pop('address')
        address = Address.objects.create(**address_data)
        return ExchangePoint.objects.create(address=address, **validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        address_data = validated_data.pop('address', None)
        if address_data is not None:
            for field, value in address_data.items():
                setattr(instance.address, field, value)
            instance.address.save()
        return super().update(instance, validated_data)
