from datetime import timedelta
from decimal import Decimal

from django.contrib.gis.geos import Point
from django.utils import timezone
from rest_framework.test import APITestCase

from exchange_points.models import Address, ExchangePoint
from exchanges.models import Exchange
from items.models import Item, ItemType
from users.models import User

from .models import InventoryRecord, PointAuditLog, PointMember


class OrganizerAndEcoTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager, cls.volunteer, cls.other, cls.client_user = [
            User.objects.create_user(email=f'{name}@example.test', username=name)
            for name in ('manager', 'volunteer', 'other', 'client')
        ]
        for street in ('Первая', 'Вторая'):
            address = Address.objects.create(city='Екатеринбург', street=street, building='1',
                                             location=Point(60.6, 56.8, srid=4326))
            point = ExchangePoint.objects.create(title=street, address=address)
            if street == 'Первая':
                cls.point = point
            else:
                PointMember.objects.create(point=point, user=cls.other, role='organizer')
        cls.kind = ItemType.objects.get(title='Детская одежда')
        cls.point.item_types.add(cls.kind)
        PointMember.objects.create(point=cls.point, user=cls.manager, role='organizer')
        PointMember.objects.create(point=cls.point, user=cls.volunteer, role='volunteer')
        PointMember.objects.create(point=cls.point, user=cls.client_user, role='volunteer')
        cls.url = f'/api/v1/organizer/points/{cls.point.pk}'

    def test_permissions_scope_inventory_and_status_to_point(self):
        self.assertEqual(self.client.get(f'{self.url}/inventory').status_code, 401)
        for actor in (self.volunteer, self.other):
            self.client.force_authenticate(actor)
            self.assertEqual(self.client.get(f'{self.url}/inventory').status_code, 403)
            self.assertEqual(self.client.patch(f'{self.url}/status', {'status': 'closed'}).status_code, 403)
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.patch(f'{self.url}/status', {'status': 'active'}).status_code, 200)
        log = PointAuditLog.objects.get(action='point.status')
        self.assertEqual(log.data, {'before': 'needs_check', 'after': 'active'})

    def test_inventory_prevents_issue_beyond_available_stock(self):
        self.client.force_authenticate(self.manager)
        url = f'{self.url}/inventory'
        payload = {'item_type': self.kind.pk, 'quantity': 2, 'client': self.client_user.pk}
        self.assertEqual(self.client.post(url, {**payload, 'direction': 'issue'}).status_code, 409)
        response = self.client.post(url, {**payload, 'direction': 'intake', 'weight_kg': '1.20'})
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['recorded_by'], self.manager.pk)
        self.assertEqual(self.client.post(url, {**payload, 'direction': 'issue'}).status_code, 201)
        self.assertEqual(self.client.post(url, {**payload, 'direction': 'issue'}).status_code, 409)
        self.assertEqual(InventoryRecord.objects.count(), 2)
        self.assertEqual(PointAuditLog.objects.count(), 2)

    def test_volunteers_can_sign_up_only_with_capacity(self):
        self.client.force_authenticate(self.manager)
        start = timezone.now() + timedelta(days=1)
        payload = {'starts_at': start.isoformat(), 'ends_at': (start + timedelta(hours=2)).isoformat(),
                   'capacity': 1}
        response = self.client.post(f'{self.url}/shifts', payload)
        self.assertEqual(response.status_code, 201, response.data)
        detail = f"{self.url}/shifts/{response.data['id']}"
        signup = f'{detail}/signup'
        self.client.force_authenticate(self.volunteer)
        self.assertEqual(self.client.post(f'{self.url}/shifts', payload).status_code, 403)
        self.assertEqual(self.client.post(signup).status_code, 201)
        self.assertEqual(self.client.post(signup).status_code, 200)
        detail_data = self.client.get(detail).data
        self.assertEqual((detail_data['occupied'], detail_data['my_status']), (1, 'signed_up'))
        self.client.force_authenticate(self.client_user)
        self.assertEqual(self.client.post(signup).status_code, 409)
        self.client.force_authenticate(self.volunteer)
        self.assertEqual(self.client.delete(signup).status_code, 204)
        self.client.force_authenticate(self.client_user)
        self.assertEqual(self.client.post(signup).status_code, 201)

    def test_eco_stats_counts_completed_giving_and_intake_once(self):
        self.assertIsNotNone(self.kind.co2_per_kg)
        self.assertEqual(self.client.get('/api/v1/me/eco-stats').status_code, 401)
        self.client.force_authenticate(self.client_user)
        self.assertEqual(self.client.get('/api/v1/me/eco-stats').data['items_count'], 0)
        item = Item.objects.create(owner=self.client_user, title='Куртка', item_type=self.kind)
        exchange = Exchange.objects.create(item=item, giver=self.client_user, receiver=self.other, status='agreed')
        self.assertEqual(self.client.get('/api/v1/me/eco-stats').data['items_count'], 0)
        exchange.complete()
        exchange.save()
        for direction in ('intake', 'issue'):
            InventoryRecord.objects.create(point=self.point, item_type=self.kind, direction=direction,
                                           quantity=2, weight_kg=Decimal('1.20'), client=self.client_user,
                                           recorded_by=self.manager)
        result = self.client.get('/api/v1/me/eco-stats').data
        self.assertEqual((result['items_count'], result['p2p_items_count'], result['point_items_count']), (3, 1, 2))
        self.assertEqual(result['estimated_weight_kg'], '1.50')
        self.assertEqual(result['estimated_co2_kg'], '6.00')
