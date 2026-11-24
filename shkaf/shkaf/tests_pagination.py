from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.utils import timezone
from drf_spectacular.generators import SchemaGenerator
from rest_framework.test import APITestCase

from bookmarks.models import Bookmark
from chat.models import Conversation, Message
from exchange_points.models import Address, ExchangePoint
from exchanges.models import Exchange
from items.models import Item, ItemType
from notifications.models import Notification, Subscription
from reviews.models import Review


class PaginationTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email='staff@example.test', username='staff', password='Xk29-test-Qz', is_staff=True,
        )
        cls.item_type = ItemType.objects.get(title='Книги')
        cls.items = []
        cls.receivers = []
        cls.conversations = []
        for number in range(25):
            receiver = get_user_model().objects.create(
                email=f'receiver{number}@example.test', username=f'receiver{number}',
            )
            cls.receivers.append(receiver)
            item = Item.objects.create(
                owner=cls.user, item_type=cls.item_type, title=f'Книга {number}',
                condition='good', exchange_format='free', status='active',
            )
            cls.items.append(item)
            Bookmark.objects.create(user=cls.user, item=item)
            conversation = Conversation.objects.create(item=item, owner=cls.user, requester=receiver)
            cls.conversations.append(conversation)
            Message.objects.create(conversation=conversation, sender=receiver, body=f'Сообщение {number}')
            given = Item.objects.create(
                owner=cls.user, item_type=cls.item_type, title=f'Переданная книга {number}',
                condition='good', exchange_format='free', status='given',
            )
            exchange = Exchange.objects.create(item=given, giver=cls.user, receiver=receiver, status='completed')
            Review.objects.create(exchange=exchange, author=receiver, target_user=cls.user, rating=5)
            Notification.objects.create(user=cls.user, type=Notification.Type.NEW_ITEM, payload={'item_id': item.pk})
            Exchange.objects.create(item=cls.items[0], giver=cls.user, receiver=receiver)
        cls.endpoints = {
            '/api/v1/items': 25,
            '/api/v1/me/items': 50,
            '/api/v1/me/bookmarks': 25,
            '/api/v1/reviews': 25,
            '/api/v1/exchanges': 50,
            f'/api/v1/items/{cls.items[0].pk}/exchanges': 25,
            '/api/v1/users/': 26,
            '/api/v1/conversations': 25,
            '/api/v1/me/notifications': 25,
        }

    def setUp(self):
        self.client.force_authenticate(self.user)

    def test_all_selected_endpoints_have_default_pagination(self):
        for url, count in self.endpoints.items():
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(set(response.data), {'count', 'next', 'previous', 'results'})
                self.assertEqual(response.data['count'], count)
                self.assertEqual(len(response.data['results']), 20)
                self.assertIsNone(response.data['previous'])
                self.assertIsNotNone(response.data['next'])

    def test_custom_page_size_navigation_and_no_overlap(self):
        for url, count in self.endpoints.items():
            with self.subTest(url=url):
                first = self.client.get(url, {'page_size': 10}).data
                second = self.client.get(first['next']).data
                last = self.client.get(url, {'page_size': 10, 'page': (count + 9) // 10}).data
                self.assertEqual(second['count'], count)
                self.assertEqual(len(second['results']), 10)
                self.assertIsNotNone(second['previous'])
                self.assertIsNone(last['next'])
                self.assertEqual(len(last['results']), count % 10 or 10)
                self.assertFalse(
                    {row['id'] for row in first['results']} & {row['id'] for row in second['results']}
                )

    def test_invalid_or_out_of_range_pages_return_404(self):
        for url in self.endpoints:
            for page in ('abc', '0', '-1', '999'):
                with self.subTest(url=url, page=page):
                    self.assertEqual(self.client.get(url, {'page': page}).status_code, 404)

    def test_page_size_is_capped_at_100(self):
        Item.objects.bulk_create([
            Item(owner=self.user, item_type=self.item_type, title=f'Ещё книга {number}',
                 condition='good', exchange_format='free', status='active')
            for number in range(100)
        ])
        response = self.client.get('/api/v1/items', {'page_size': 1000})
        self.assertEqual(response.data['count'], 125)
        self.assertEqual(len(response.data['results']), 100)
        self.assertIsNotNone(response.data['next'])

    def test_invalid_page_sizes_use_default(self):
        for size in ('abc', '0', '-1'):
            response = self.client.get('/api/v1/items', {'page_size': size})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.data['results']), 20)

    def test_filtering_happens_before_pagination_and_links_preserve_filters(self):
        response = self.client.get('/api/v1/items', {
            'owner_id': self.user.pk, 'item_type': 'Книги', 'search': 'Книга',
            'ordering': 'created_at', 'page_size': 2,
        })
        self.assertEqual(response.data['count'], 25)
        params = parse_qs(urlparse(response.data['next']).query)
        self.assertEqual(params['owner_id'], [str(self.user.pk)])
        self.assertEqual(params['item_type'], ['Книги'])
        self.assertEqual(params['search'], ['Книга'])
        self.assertEqual(params['ordering'], ['created_at'])
        self.assertEqual(params['page_size'], ['2'])
        second = self.client.get(response.data['next'])
        self.assertEqual([row['id'] for row in second.data['results']], [item.pk for item in self.items[2:4]])

    def test_empty_page_has_empty_results_and_no_links(self):
        response = self.client.get('/api/v1/items', {'owner_id': 999999})
        self.assertEqual(response.data, {'count': 0, 'next': None, 'previous': None, 'results': []})

    def test_tied_timestamps_have_stable_ordering(self):
        ids = [item.pk for item in self.items]
        Item.objects.filter(pk__in=ids).update(created_at=timezone.now())
        for ordering, expected in ((None, ids[::-1]), ('created_at', ids), ('-created_at', ids[::-1])):
            actual = []
            for page in range(1, 6):
                params = {'page_size': 5, 'page': page}
                if ordering:
                    params['ordering'] = ordering
                response = self.client.get('/api/v1/items', params)
                actual.extend(row['id'] for row in response.data['results'])
            self.assertEqual(actual, expected)

    def test_geo_ordering_is_preserved(self):
        Item.objects.filter(pk__in=[item.pk for item in self.items]).update(
            approx_location=Point(60.6, 56.84, srid=4326),
        )
        response = self.client.get('/api/v1/items', {
            'lat': 56.84, 'lng': 60.6, 'radius': 1, 'page_size': 2, 'page': 2,
        })
        self.assertEqual(response.data['count'], 25)
        self.assertEqual([row['id'] for row in response.data['results']], [item.pk for item in self.items[2:4]])
        self.assertTrue(all(row['distance'] == 0 for row in response.data['results']))

    def test_private_counts_and_results_remain_scoped_to_current_user(self):
        self.client.force_authenticate(self.receivers[0])
        for url in ('/api/v1/me/items', '/api/v1/me/bookmarks', '/api/v1/me/notifications'):
            self.assertEqual(self.client.get(url).data['count'], 0)
        self.assertEqual(self.client.get('/api/v1/conversations').data['count'], 1)
        self.assertEqual(self.client.get('/api/v1/exchanges').data['count'], 2)
        self.assertEqual(self.client.get(f'/api/v1/items/{self.items[0].pk}/exchanges').data['count'], 1)
        self.assertEqual(self.client.get('/api/v1/users/').status_code, 403)

    def test_conversation_page_keeps_last_message_and_unread_count(self):
        response = self.client.get('/api/v1/conversations', {'page_size': 2, 'page': 2})
        self.assertEqual(len(response.data['results']), 2)
        for row in response.data['results']:
            conversation = Conversation.objects.get(pk=row['id'])
            message = conversation.messages.get()
            self.assertEqual(row['last_message']['id'], message.pk)
            self.assertEqual(row['unread_count'], 1)

    def test_unselected_lists_and_detail_responses_are_not_paginated(self):
        ExchangePoint.objects.create(
            title='Пункт', address=Address.objects.create(
                city='Екатеринбург', street='Мира', building='19', location=Point(60.65, 56.84, srid=4326),
            ),
        )
        Subscription.objects.create(user=self.user)
        conversation = self.conversations[0]
        Message.objects.create(conversation=conversation, sender=self.user, body='Ответ')
        for url in ('/api/v1/itemTypes', '/api/v1/exchangePoints', '/api/v1/me/subscriptions',
                    f'/api/v1/conversations/{conversation.pk}/messages'):
            response = self.client.get(url, {'page_size': 1, 'page': 999})
            self.assertEqual(response.status_code, 200)
            self.assertIsInstance(response.data, list)
        self.assertEqual(
            len(self.client.get(f'/api/v1/conversations/{conversation.pk}/messages').data), 2,
        )
        for url in (f'/api/v1/items/{self.items[0].pk}', f'/api/v1/users/{self.user.pk}',
                    f'/api/v1/conversations/{conversation.pk}'):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertIn('id', response.data)
            self.assertNotIn('results', response.data)
        self.assertEqual(self.client.get('/api/v1/me/notifications/unread-count').data, {'count': 25})

    def test_openapi_describes_pagination_only_for_selected_lists(self):
        schema = SchemaGenerator().get_schema(public=True)
        paths = (
            '/api/v1/items', '/api/v1/me/items', '/api/v1/me/bookmarks', '/api/v1/reviews',
            '/api/v1/exchanges', '/api/v1/items/{item_id}/exchanges', '/api/v1/users/',
            '/api/v1/conversations', '/api/v1/me/notifications',
        )
        for path in paths:
            operation = schema['paths'][path]['get']
            parameters = {p['name'] for p in operation['parameters']}
            self.assertTrue({'page', 'page_size'} <= parameters, path)
            response = operation['responses']['200']['content']['application/json']['schema']
            component = schema['components']['schemas'][response['$ref'].split('/')[-1]]
            self.assertIn('results', component['properties'])
        for path in ('/api/v1/exchangePoints', '/api/v1/itemTypes', '/api/v1/me/subscriptions',
                     '/api/v1/conversations/{id}/messages'):
            parameters = {p['name'] for p in schema['paths'][path]['get'].get('parameters', [])}
            self.assertFalse({'page', 'page_size'} & parameters, path)
