import math

from django.contrib.gis.geos import Point
from rest_framework import serializers


def coordinates_to_point(attrs, field):
    """Собирает Point из пары latitude и longitude, переданных через source='<field>.y' и '<field>.x'."""
    if field not in attrs:
        return attrs
    coordinates = attrs[field]
    if set(coordinates) != {'x', 'y'}:
        raise serializers.ValidationError('Both latitude and longitude are required.')
    if coordinates['x'] is None and coordinates['y'] is None:
        attrs[field] = None
        return attrs
    if coordinates['x'] is None or coordinates['y'] is None:
        raise serializers.ValidationError('Both latitude and longitude are required.')
    if not all(math.isfinite(value) for value in coordinates.values()):
        raise serializers.ValidationError('Coordinates must be finite numbers.')
    attrs[field] = Point(coordinates['x'], coordinates['y'], srid=4326)
    return attrs
