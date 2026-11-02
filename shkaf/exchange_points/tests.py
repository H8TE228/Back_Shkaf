from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.test import TestCase

from .models import Address


class AddressGeoTests(TestCase):
    def setUp(self):
        self.center = Address.objects.create(
            city='Екатеринбург', street='Мира', building='19', location=Point(60.6522, 56.8440, srid=4326)
        )
        self.far = Address.objects.create(
            city='Москва', street='Тверская', building='1', location=Point(37.6156, 55.7522, srid=4326)
        )

    def test_radius_search_uses_postgis(self):
        origin = Point(60.6057, 56.8389, srid=4326)
        found = Address.objects.filter(location__distance_lte=(origin, D(km=10)))
        self.assertEqual(list(found), [self.center])

    def test_distance_is_in_meters(self):
        origin = Point(60.6057, 56.8389, srid=4326)
        address = Address.objects.annotate(distance=Distance('location', origin)).get(pk=self.center.pk)
        self.assertGreater(address.distance.m, 2000)
        self.assertLess(address.distance.m, 4000)
