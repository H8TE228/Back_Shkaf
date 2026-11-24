from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.test import TransactionTestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from items.models import Item, ItemType
from shkaf.asgi import application

from .models import Notification, Subscription
from .tasks import notify_subscribers

User = get_user_model()
CENTER = Point(60.6057, 56.8389, srid=4326)
NEAR = Point(60.6057, 56.8434, srid=4326)   # примерно 500 м от центра
FAR = Point(60.6057, 56.9289, srid=4326)    # примерно 10 км от центра


def make_user(name):
    return User.objects.create_user(email=f'{name}@example.test', username=name, password='Xk29-test-Qz')


class NotificationTestCase(APITestCase):
    def setUp(self):
        self.owner, self.subscriber = make_user('owner'), make_user('subscriber')
        self.shoes = ItemType.objects.get(title='Обувь')
        self.books = ItemType.objects.get(title='Книги')

    def make_item(self, **kwargs):
        defaults = {'owner': self.owner, 'item_type': self.shoes, 'title': 'Кроссовки', 'condition': 'good',
                    'exchange_format': 'free', 'status': 'active'}
        return Item.objects.create(**{**defaults, **kwargs})

    def subscribe(self, user=None, **kwargs):
        return Subscription.objects.create(user=user or self.subscriber, **kwargs)

    def notified(self, user=None):
        return list(Notification.objects.filter(user=user or self.subscriber, type='new_item')
                    .values_list('payload__item_id', flat=True))


class SubscriptionMatchingTests(NotificationTestCase):
    def test_conditions(self):
        cases = [
            ({}, {}, True),
            ({'item_type': self.shoes}, {}, True),
            ({'item_type': self.books}, {}, False),
            ({'exchange_format': 'free'}, {}, True),
            ({'exchange_format': 'swap'}, {}, False),
            ({'query': 'КРОСС'}, {}, True),
            ({'query': 'куртка'}, {'description': 'Есть ещё куртка'}, True),
            ({'query': 'стол'}, {}, False),
            ({'center': CENTER, 'radius_km': 1}, {'approx_location': NEAR}, True),
            ({'center': CENTER, 'radius_km': 1}, {'approx_location': FAR}, False),
            ({'center': CENTER, 'radius_km': 1}, {}, False),
            ({'is_active': False}, {}, False),
        ]
        for number, (subscription, item_fields, expected) in enumerate(cases):
            Subscription.objects.all().delete()
            Notification.objects.all().delete()
            self.subscribe(**subscription)
            item = self.make_item(title=f'Кроссовки {number}', **item_fields)
            notify_subscribers(item.pk)
            self.assertEqual(self.notified() == [item.pk], expected, (subscription, item_fields))

    def test_owner_and_deleted_users_are_not_notified(self):
        self.subscribe(user=self.owner)
        self.subscribe()
        self.subscriber.anonymize()
        notify_subscribers(self.make_item().pk)
        self.assertFalse(Notification.objects.exists())

    def test_one_notification_per_user(self):
        self.subscribe()
        self.subscribe(item_type=self.shoes)
        self.assertEqual(notify_subscribers(self.make_item().pk), 1)

    def test_not_active_item_is_ignored(self):
        self.subscribe()
        self.assertEqual(notify_subscribers(self.make_item(status='draft').pk), 0)


class PublishingTriggersNotificationsTests(NotificationTestCase):
    def payload(self, **kwargs):
        return {'item_type': self.shoes.pk, 'title': 'Кроссовки', 'condition': 'good', 'exchange_format': 'free',
                **kwargs}

    def test_creating_active_item_notifies(self):
        self.subscribe()
        self.client.force_authenticate(self.owner)
        with self.captureOnCommitCallbacks(execute=True):
            item_id = self.client.post('/api/v1/items', self.payload(status='active'), format='json').data['id']
        self.assertEqual(self.notified(), [item_id])

    def test_draft_notifies_only_when_published(self):
        self.subscribe()
        self.client.force_authenticate(self.owner)
        with self.captureOnCommitCallbacks(execute=True):
            item_id = self.client.post('/api/v1/items', self.payload(), format='json').data['id']
        self.assertEqual(self.notified(), [])
        with self.captureOnCommitCallbacks(execute=True):
            self.client.patch(f'/api/v1/items/{item_id}', {'status': 'active'}, format='json')
        self.assertEqual(self.notified(), [item_id])
        with self.captureOnCommitCallbacks(execute=True):
            self.client.patch(f'/api/v1/items/{item_id}', {'title': 'Новое название'}, format='json')
        self.assertEqual(self.notified(), [item_id])


class ExchangeNotificationsTests(NotificationTestCase):
    def types(self, user):
        return list(Notification.objects.filter(user=user).order_by('pk').values_list('type', flat=True))

    def test_exchange_events(self):
        item = self.make_item()
        self.client.force_authenticate(self.subscriber)
        exchange_id = self.client.post(f'/api/v1/items/{item.pk}/exchanges').data['id']
        self.client.force_authenticate(self.owner)
        self.client.post(f'/api/v1/exchanges/{exchange_id}/agree')
        self.client.post(f'/api/v1/exchanges/{exchange_id}/confirm')
        self.client.force_authenticate(self.subscriber)
        self.client.post(f'/api/v1/exchanges/{exchange_id}/confirm')
        self.assertEqual(self.types(self.owner), ['exchange_requested', 'exchange_completed'])
        self.assertEqual(self.types(self.subscriber), ['exchange_agreed', 'exchange_completed'])
        payload = Notification.objects.filter(user=self.owner).first().payload
        self.assertEqual(payload, {'exchange_id': exchange_id, 'item_id': item.pk, 'item_title': 'Кроссовки'})

    def test_decline_and_auto_decline_notify_receivers(self):
        item = self.make_item()
        other = make_user('other')
        ids = {}
        for user in (self.subscriber, other):
            self.client.force_authenticate(user)
            ids[user.pk] = self.client.post(f'/api/v1/items/{item.pk}/exchanges').data['id']
        self.client.force_authenticate(self.owner)
        self.client.post(f'/api/v1/exchanges/{ids[other.pk]}/decline')
        self.client.patch(f'/api/v1/items/{item.pk}', {'status': 'archived'}, format='json')
        self.assertEqual(self.types(other), ['exchange_declined'])
        self.assertEqual(self.types(self.subscriber), ['exchange_declined'])

    def test_cancel_notifies_other_side(self):
        item = self.make_item()
        self.client.force_authenticate(self.subscriber)
        exchange_id = self.client.post(f'/api/v1/items/{item.pk}/exchanges').data['id']
        self.client.post(f'/api/v1/exchanges/{exchange_id}/cancel')
        self.assertEqual(self.types(self.owner), ['exchange_requested', 'exchange_cancelled'])


class SubscriptionApiTests(NotificationTestCase):
    url = '/api/v1/me/subscriptions'

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.subscriber)

    def test_requires_auth(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_crud(self):
        response = self.client.post(self.url, {
            'item_type': self.shoes.pk, 'exchange_format': 'free', 'query': 'кроссовки',
            'latitude': 56.8389, 'longitude': 60.6057, 'radius_km': 5,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertAlmostEqual(response.data['latitude'], 56.8389)
        detail = f'{self.url}/{response.data["id"]}'
        self.assertEqual(self.client.patch(detail, {'is_active': False}, format='json').data['is_active'], False)
        response = self.client.patch(detail, {'latitude': None, 'longitude': None, 'radius_km': None}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(response.data['latitude'])
        self.assertEqual(len(self.client.get(self.url).data), 1)
        self.assertEqual(self.client.delete(detail).status_code, status.HTTP_204_NO_CONTENT)

    def test_validation(self):
        for data in ({'latitude': 56.8, 'longitude': 60.6}, {'radius_km': 5}, {'exchange_format': 'charity'},
                     {'latitude': 56.8, 'longitude': 60.6, 'radius_km': 51}, {'item_type': 9999}):
            self.assertEqual(self.client.post(self.url, data, format='json').status_code, 400, data)

    def test_limit_per_user(self):
        for _ in range(20):
            self.assertEqual(self.client.post(self.url, {}, format='json').status_code, 201)
        self.assertEqual(self.client.post(self.url, {}, format='json').status_code, 400)

    def test_foreign_subscription_is_hidden(self):
        foreign = self.subscribe(user=self.owner)
        self.assertEqual(self.client.get(f'{self.url}/{foreign.pk}').status_code, 404)
        self.assertEqual(self.client.delete(f'{self.url}/{foreign.pk}').status_code, 404)


class NotificationApiTests(NotificationTestCase):
    url = '/api/v1/me/notifications'

    def setUp(self):
        super().setUp()
        for number in range(3):
            Notification.objects.create(user=self.subscriber, type='new_item', payload={'item_id': number})
        self.foreign = Notification.objects.create(user=self.owner, type='new_item', payload={})
        self.client.force_authenticate(self.subscriber)

    def test_list_and_unread(self):
        self.assertEqual(len(self.client.get(self.url).data['results']), 3)
        self.assertEqual(self.client.get(f'{self.url}/unread-count').data, {'count': 3})
        first = self.client.get(self.url).data['results'][0]['id']
        self.assertIsNotNone(self.client.post(f'{self.url}/{first}/read').data['read_at'])
        self.assertEqual(len(self.client.get(self.url, {'unread': 'true'}).data['results']), 2)
        self.assertEqual(self.client.post(f'{self.url}/read-all').data, {'marked_read': 2})
        self.assertEqual(self.client.get(f'{self.url}/unread-count').data, {'count': 0})

    def test_foreign_notification_is_hidden(self):
        self.assertEqual(self.client.post(f'{self.url}/{self.foreign.pk}/read').status_code, 404)
        self.client.post(f'{self.url}/read-all')
        self.foreign.refresh_from_db()
        self.assertIsNone(self.foreign.read_at)


@override_settings(CHANNEL_LAYERS={'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}})
class NotificationWebSocketTests(TransactionTestCase):
    serialized_rollback = True

    def setUp(self):
        self.owner, self.subscriber = make_user('owner'), make_user('subscriber')
        self.item_type, _ = ItemType.objects.get_or_create(title='Обувь')

    def socket(self, user=None):
        headers = [(b'origin', b'http://localhost:8000')]
        if user is not None:
            headers.append((b'cookie', f'access_token={AccessToken.for_user(user)}'.encode()))
        return WebsocketCommunicator(application, '/ws/notifications', headers=headers)

    async def test_anonymous_is_closed_with_4401(self):
        socket = self.socket()
        self.assertTrue((await socket.connect())[0])
        output = await socket.receive_output(timeout=3)
        self.assertEqual(output.get('code'), 4401)

    async def test_new_item_notification_is_pushed(self):
        from channels.db import database_sync_to_async

        socket = self.socket(self.subscriber)
        self.assertTrue((await socket.connect())[0])
        await database_sync_to_async(Subscription.objects.create)(user=self.subscriber)
        item = await database_sync_to_async(Item.objects.create)(
            owner=self.owner, item_type=self.item_type, title='Кроссовки', condition='good',
            exchange_format='free', status='active',
        )
        await database_sync_to_async(notify_subscribers)(item.pk)
        event = await socket.receive_json_from(timeout=3)
        self.assertEqual(event['type'], 'notification')
        self.assertEqual(event['notification']['payload']['item_id'], item.pk)
        await socket.disconnect()
