from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from rest_framework.test import APITestCase

from exchange_points.models import Address, ExchangePoint
from items.models import Item, ItemType

User = get_user_model()
# Центр Екатеринбурга и точки на известном расстоянии от него
CENTER = {'lat': 56.8389, 'lng': 60.6057}
NEAR = Point(60.6057, 56.8434, srid=4326)       # примерно 500 м на север
MIDDLE = Point(60.6057, 56.8659, srid=4326)     # примерно 3 км на север
FAR = Point(60.6057, 56.9289, srid=4326)        # примерно 10 км на север


class GeoTestCase(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email='owner@example.test', username='owner', password='Xk29-test-Qz')
        self.item_type = ItemType.objects.get(title='Обувь')

    def make_item(self, title, location, **kwargs):
        return Item.objects.create(
            owner=self.owner, item_type=self.item_type, title=title, condition='good',
            exchange_format='free', status='active', approx_location=location, **kwargs,
        )

    def make_point(self, title, location):
        return ExchangePoint.objects.create(
            title=title, status='active',
            address=Address.objects.create(city='Екатеринбург', street='Ленина', building=title, location=location),
        )


class ItemDistanceSearchTests(GeoTestCase):
    def setUp(self):
        super().setUp()
        self.far = self.make_item('Далеко', FAR)
        self.near = self.make_item('Близко', NEAR)
        self.middle = self.make_item('Средне', MIDDLE)
        self.nowhere = self.make_item('Без координат', None)

    def search(self, **params):
        return self.client.get('/api/v1/items', {**CENTER, **params})

    def test_default_radius_is_5_km_and_sorted_by_distance(self):
        response = self.search()
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item['title'] for item in response.data], ['Близко', 'Средне'])
        self.assertLess(response.data[0]['distance'], response.data[1]['distance'])
        self.assertAlmostEqual(response.data[1]['distance'], 3000, delta=300)

    def test_custom_radius(self):
        self.assertEqual([i['title'] for i in self.search(radius=1).data], ['Близко'])
        self.assertEqual([i['title'] for i in self.search(radius=20).data], ['Близко', 'Средне', 'Далеко'])

    def test_ordering_param_overrides_distance_order(self):
        titles = [item['title'] for item in self.search(radius=20, ordering='-created_at').data]
        self.assertEqual(titles, ['Средне', 'Близко', 'Далеко'])

    def test_combines_with_other_filters(self):
        self.middle.exchange_format = 'swap'
        self.middle.save()
        response = self.search(exchange_format='swap')
        self.assertEqual([item['title'] for item in response.data], ['Средне'])

    def test_without_geo_params_distance_is_null(self):
        response = self.client.get('/api/v1/items')
        self.assertEqual(len(response.data), 4)
        self.assertTrue(all(item['distance'] is None for item in response.data))

    def test_invalid_params(self):
        for params in [{'lat': 56.8}, {'lng': 60.6}, {'radius': 3}, {'lat': 'abc', 'lng': 60},
                       {'lat': 91, 'lng': 60}, {'lat': 56, 'lng': 181}, {**CENTER, 'radius': 0},
                       {**CENTER, 'radius': 51}, {'lat': 'nan', 'lng': 60}]:
            response = self.client.get('/api/v1/items', params)
            self.assertEqual(response.status_code, 400, params)

    def test_my_items_support_distance(self):
        self.client.force_authenticate(self.owner)
        response = self.client.get('/api/v1/me/items', {**CENTER, 'radius': 1})
        self.assertEqual([item['title'] for item in response.data], ['Близко'])


class ItemCoordinatesTests(GeoTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.owner)

    def payload(self, **kwargs):
        return {'item_type': self.item_type.pk, 'title': 'Куртка', 'condition': 'good',
                'exchange_format': 'free', **kwargs}

    def test_coordinates_are_saved_rounded(self):
        response = self.client.post('/api/v1/items', self.payload(latitude=56.83892, longitude=60.60571), format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertAlmostEqual(response.data['latitude'], 56.84)
        self.assertAlmostEqual(response.data['longitude'], 60.605)

    def test_coordinates_are_optional(self):
        response = self.client.post('/api/v1/items', self.payload(), format='json')
        self.assertEqual(response.status_code, 201)
        self.assertIsNone(response.data['latitude'])

    def test_both_coordinates_are_required(self):
        response = self.client.post('/api/v1/items', self.payload(latitude=56.8), format='json')
        self.assertEqual(response.status_code, 400)

    def test_invalid_coordinates(self):
        for coordinates in [{'latitude': 91, 'longitude': 60}, {'latitude': 'NaN', 'longitude': 60}]:
            response = self.client.post('/api/v1/items', self.payload(**coordinates), format='json')
            self.assertEqual(response.status_code, 400, coordinates)

    def test_coordinates_can_be_changed_and_cleared(self):
        item = self.make_item('Куртка', NEAR)
        url = f'/api/v1/items/{item.pk}'
        response = self.client.patch(url, {'latitude': 56.9289, 'longitude': 60.6057}, format='json')
        self.assertAlmostEqual(response.data['latitude'], 56.93)
        response = self.client.patch(url, {'latitude': None, 'longitude': None}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data['latitude'])
        item.refresh_from_db()
        self.assertIsNone(item.approx_location)

    def test_patch_without_coordinates_keeps_them(self):
        item = self.make_item('Куртка', NEAR)
        response = self.client.patch(f'/api/v1/items/{item.pk}', {'title': 'Новая'}, format='json')
        self.assertIsNotNone(response.data['latitude'])


class ExchangePointDistanceSearchTests(GeoTestCase):
    def setUp(self):
        super().setUp()
        self.make_point('Далеко', FAR)
        self.make_point('Близко', NEAR)
        self.make_point('Средне', MIDDLE)

    def test_search_and_order(self):
        response = self.client.get('/api/v1/exchangePoints', CENTER)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([point['title'] for point in response.data], ['Близко', 'Средне'])
        self.assertAlmostEqual(response.data[0]['distance'], 500, delta=100)

    def test_invalid_params(self):
        self.assertEqual(self.client.get('/api/v1/exchangePoints', {'lat': 56.8}).status_code, 400)

    def test_without_geo_params_distance_is_null(self):
        response = self.client.get('/api/v1/exchangePoints')
        self.assertEqual(len(response.data), 3)
        self.assertTrue(all(point['distance'] is None for point in response.data))
