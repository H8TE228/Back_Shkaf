import math

from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from rest_framework import serializers
from rest_framework.filters import BaseFilterBackend

DEFAULT_RADIUS_KM = 5
MAX_RADIUS_KM = 50


class DistanceFilter(BaseFilterBackend):
    """
    Поиск «рядом со мной»: ?lat=&lng=&radius= (радиус в км).
    Оставляет объекты в радиусе, добавляет к ним distance в метрах и сортирует по расстоянию,
    если не передан ?ordering=. Поле с координатами задаётся во view атрибутом distance_field.
    """

    def filter_queryset(self, request, queryset, view):
        params = request.query_params
        if not any(name in params for name in ('lat', 'lng', 'radius')):
            return queryset

        latitude = self.number(params, 'lat', -90, 90)
        longitude = self.number(params, 'lng', -180, 180)
        radius = self.number(params, 'radius', 0.1, MAX_RADIUS_KM, default=DEFAULT_RADIUS_KM)
        point = Point(longitude, latitude, srid=4326)
        field = view.distance_field

        queryset = queryset.filter(**{f'{field}__distance_lte': (point, D(km=radius))})
        queryset = queryset.annotate(distance=Distance(field, point))
        if 'ordering' not in params:
            queryset = queryset.order_by('distance', 'pk')
        return queryset

    @staticmethod
    def number(params, name, minimum, maximum, default=None):
        raw = params.get(name)
        if raw in (None, ''):
            if default is not None:
                return default
            raise serializers.ValidationError({name: 'lat and lng are required for the distance search.'})
        try:
            value = float(raw)
        except ValueError:
            raise serializers.ValidationError({name: 'A number is required.'}) from None
        if not math.isfinite(value) or not minimum <= value <= maximum:
            raise serializers.ValidationError({name: f'Must be between {minimum} and {maximum}.'})
        return value

    def get_schema_operation_parameters(self, view):
        description = 'Поиск рядом: широта и долгота центра, радиус в км (по умолчанию {}, максимум {}).'.format(
            DEFAULT_RADIUS_KM, MAX_RADIUS_KM
        )
        return [
            {'name': name, 'required': False, 'in': 'query', 'description': description,
             'schema': {'type': 'number'}}
            for name in ('lat', 'lng', 'radius')
        ]


class DistanceSerializerMixin(serializers.Serializer):
    distance = serializers.SerializerMethodField(
        help_text='Расстояние в метрах, есть только при поиске с lat и lng'
    )

    def get_distance(self, obj) -> int | None:
        distance = getattr(obj, 'distance', None)
        return None if distance is None else round(distance.m)
