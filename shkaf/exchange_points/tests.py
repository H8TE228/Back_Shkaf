from django.contrib.auth import get_user_model
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Address, ExchangePoint


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


class ExchangePointModelTests(TestCase):
    def setUp(self):
        self.address = Address.objects.create(
            city='Екатеринбург', street='Мира', building='19', location=Point(60.6522, 56.8440, srid=4326)
        )

    def test_defaults_and_string_representation(self):
        point = ExchangePoint.objects.create(address=self.address, title='Добрый Шкаф')
        point.refresh_from_db()
        self.assertEqual(str(point), 'Добрый Шкаф')
        self.assertEqual(point.status, ExchangePoint.Status.NEEDS_CHECK)
        self.assertEqual(point.formats, [])
        self.assertEqual(point.opening_hours, {})
        self.assertIsNone(point.verified_by)

    def test_address_belongs_to_only_one_point(self):
        ExchangePoint.objects.create(address=self.address, title='Первый')
        with self.assertRaises(IntegrityError), transaction.atomic():
            ExchangePoint.objects.create(address=self.address, title='Второй')

    def test_address_is_protected(self):
        ExchangePoint.objects.create(address=self.address, title='Добрый Шкаф')
        with self.assertRaises(ProtectedError):
            self.address.delete()

    def test_formats_and_verifier(self):
        user = get_user_model().objects.create_user(
            email='moderator@example.test', username='moderator', password='Xk29-test-Qz'
        )
        point = ExchangePoint.objects.create(
            address=self.address, title='Добрый Шкаф',
            formats=[ExchangePoint.Format.FREE, ExchangePoint.Format.CHARITY], verified_by=user,
        )
        point.refresh_from_db()
        self.assertEqual(point.formats, ['free', 'charity'])
        self.assertEqual(point.verified_by, user)
        user.delete()
        point.refresh_from_db()
        self.assertIsNone(point.verified_by)


class ExchangePointApiTests(APITestCase):
    url = '/api/v1/exchange-points'

    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            email='staff@example.test', username='staff', password='Xk29-test-Qz', is_staff=True
        )
        self.user = get_user_model().objects.create_user(
            email='user@example.test', username='user', password='Xk29-test-Qz', role='admin'
        )
        self.address = Address.objects.create(
            city='Екатеринбург', district='Кировский', street='Мира', building='19',
            location=Point(60.6522, 56.8440, srid=4326),
        )
        self.point = ExchangePoint.objects.create(
            address=self.address, title='Добрый Шкаф', status=ExchangePoint.Status.ACTIVE,
            formats=['free', 'charity'],
        )

    def payload(self, **kwargs):
        return {
            'title': 'Новый пункт',
            'address': {
                'city': 'Екатеринбург', 'street': 'Ленина', 'building': '1',
                'latitude': 56.84, 'longitude': 60.60,
            },
            **kwargs,
        }

    def test_all_statuses_are_public(self):
        for point_status in [ExchangePoint.Status.NEEDS_CHECK, ExchangePoint.Status.CLOSED]:
            address = Address.objects.create(
                city='Москва', street='Мира', building='1', location=Point(37.6, 55.7, srid=4326)
            )
            ExchangePoint.objects.create(address=address, title=point_status, status=point_status)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual({point['status'] for point in response.data}, {'active', 'needs_check', 'closed'})
        for point in response.data:
            self.assertEqual(self.client.get(f'{self.url}/{point["id"]}').status_code, 200)

    def test_retrieve_contains_address_and_coordinates(self):
        response = self.client.get(f'{self.url}/{self.point.pk}')
        self.assertEqual(response.data['address']['latitude'], 56.844)
        self.assertEqual(response.data['address']['longitude'], 60.6522)
        self.assertEqual(response.data['formats'], ['free', 'charity'])

    def test_only_staff_can_write(self):
        detail = f'{self.url}/{self.point.pk}'
        self.assertEqual(self.client.post(self.url, self.payload(), format='json').status_code, 401)
        self.assertEqual(self.client.patch(detail, {'title': 'X'}, format='json').status_code, 401)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.post(self.url, self.payload(), format='json').status_code, 403)
        self.assertEqual(self.client.patch(detail, {'title': 'X'}, format='json').status_code, 403)
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.post(self.url, self.payload(), format='json').status_code, 201)
        self.assertEqual(self.client.patch(detail, {'title': 'X'}, format='json').status_code, 200)
        self.assertEqual(self.client.delete(detail).status_code, 405)
        self.assertEqual(self.client.put(detail, self.payload(), format='json').status_code, 405)

    def test_create_point_with_address_and_schedule(self):
        self.client.force_authenticate(self.staff)
        schedule = {
            'mon': [{'from': '22:00', 'to': '24:00'}],
            'tue': [{'from': '00:00', 'to': '02:00'}],
            'wed': [],
        }
        response = self.client.post(self.url, self.payload(
            opening_hours=schedule, formats=['free', 'points'], verified_by=self.user.pk,
            verified_at='2026-01-01T00:00:00Z',
        ), format='json')
        self.assertEqual(response.status_code, 201, response.data)
        point = ExchangePoint.objects.get(pk=response.data['id'])
        self.assertEqual(point.opening_hours, schedule)
        self.assertEqual(response.data['opening_hours'], schedule)
        self.assertEqual(point.status, 'needs_check')
        self.assertIsNone(point.verified_by)
        self.assertIsNone(point.verified_at)
        self.assertEqual(point.address.location.x, 60.6)
        self.assertEqual(point.address.location.y, 56.84)

    def test_partial_update_address_and_schedule(self):
        self.client.force_authenticate(self.staff)
        response = self.client.patch(f'{self.url}/{self.point.pk}', {
            'address': {'district': 'Ленинский', 'latitude': 55.1, 'longitude': 37.2},
            'opening_hours': {'fri': [{'from': '00:00', 'to': '24:00'}]},
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.address.refresh_from_db()
        self.assertEqual(self.address.city, 'Екатеринбург')
        self.assertEqual(self.address.district, 'Ленинский')
        self.assertEqual(self.address.location.x, 37.2)
        self.assertEqual(self.address.location.y, 55.1)
        self.assertEqual(response.data['opening_hours'], {'fri': [{'from': '00:00', 'to': '24:00'}]})

    def test_invalid_coordinates_are_rejected(self):
        self.client.force_authenticate(self.staff)
        for coordinates in [
            {'latitude': 91, 'longitude': 60}, {'latitude': 50, 'longitude': 181},
            {'latitude': 50}, {'latitude': 'NaN', 'longitude': 60},
        ]:
            response = self.client.patch(f'{self.url}/{self.point.pk}', {'address': coordinates}, format='json')
            self.assertEqual(response.status_code, 400, (coordinates, response.data))

    def test_invalid_schedule_is_rejected(self):
        self.client.force_authenticate(self.staff)
        invalid_schedules = [
            {'monday': []}, {'mon': [{'from': '24:00', 'to': '24:00'}]},
            {'mon': [{'from': '10:00', 'to': '24:01'}]},
            {'mon': [{'from': '22:00', 'to': '02:00'}]},
            {'mon': [{'from': '10:00'}]}, {'mon': [{'from': '10:00', 'to': '10:00'}]},
            {'mon': [{'from': '10:00', 'to': '12:00'}, {'from': '11:00', 'to': '13:00'}]},
        ]
        for schedule in invalid_schedules:
            response = self.client.patch(
                f'{self.url}/{self.point.pk}', {'opening_hours': schedule}, format='json'
            )
            self.assertEqual(response.status_code, 400, (schedule, response.data))

    def test_invalid_data_does_not_create_address(self):
        self.client.force_authenticate(self.staff)
        response = self.client.post(self.url, self.payload(formats=['unknown']), format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Address.objects.count(), 1)

    def test_filter_and_search(self):
        for params in [
            {'city': 'Екатеринбург'}, {'district': 'Кировский'}, {'status': 'active'},
            {'exchange_format': 'charity'}, {'search': 'шкаф'},
        ]:
            response = self.client.get(self.url, params)
            self.assertEqual(response.status_code, 200, (params, response.data))
            self.assertEqual([point['id'] for point in response.data], [self.point.pk])
        self.assertEqual(self.client.get(self.url, {'exchange_format': 'points'}).data, [])
        self.assertEqual(self.client.get(self.url, {'exchange_format': 'unknown'}).status_code, 400)
