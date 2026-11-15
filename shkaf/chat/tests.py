import asyncio

from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from items.models import Item, ItemPhoto, ItemType
from shkaf.asgi import application

from .models import MAX_MESSAGE_LENGTH, Conversation, Message

User = get_user_model()
IN_MEMORY_LAYER = {'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}}


def make_users():
    return [
        User.objects.create_user(email=f'{name}@example.test', username=name, password='Xk29-test-Qz')
        for name in ('owner', 'requester', 'stranger')
    ]


def make_item(owner, **kwargs):
    item_type, _ = ItemType.objects.get_or_create(title='Обувь')
    defaults = {'title': 'Кроссовки', 'condition': 'good', 'exchange_format': 'free', 'status': 'active'}
    return Item.objects.create(owner=owner, item_type=item_type, **{**defaults, **kwargs})


class ConversationModelTests(TestCase):
    def setUp(self):
        self.owner, self.requester, _ = make_users()
        self.item = make_item(self.owner)

    def test_one_conversation_per_item_and_requester(self):
        Conversation.objects.create(item=self.item, owner=self.owner, requester=self.requester)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Conversation.objects.create(item=self.item, owner=self.owner, requester=self.requester)

    def test_owner_cannot_be_requester(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Conversation.objects.create(item=self.item, owner=self.owner, requester=self.owner)

    def test_message_body_limits_in_database(self):
        conversation = Conversation.objects.create(item=self.item, owner=self.owner, requester=self.requester)
        for body in ['', 'x' * (MAX_MESSAGE_LENGTH + 1)]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                Message.objects.create(conversation=conversation, sender=self.owner, body=body)


class ConversationApiTests(APITestCase):
    url = '/api/v1/conversations'

    def setUp(self):
        self.owner, self.requester, self.stranger = make_users()
        self.item = make_item(self.owner)

    def start(self, user=None, item=None):
        self.client.force_authenticate(user or self.requester)
        return self.client.post(self.url, {'item_id': (item or self.item).pk}, format='json')

    def test_requires_auth(self):
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)
        response = self.client.post(self.url, {'item_id': self.item.pk}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_start_conversation(self):
        response = self.start()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['owner_id'], self.owner.pk)
        self.assertEqual(response.data['requester_id'], self.requester.pk)
        self.assertEqual(response.data['companion']['id'], self.owner.pk)
        self.assertEqual(response.data['item']['title'], 'Кроссовки')
        self.assertIsNone(response.data['last_message'])

    def test_second_start_returns_existing(self):
        first = self.start()
        second = self.start()
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data['id'], second.data['id'])
        self.assertEqual(Conversation.objects.count(), 1)

    def test_cannot_start_about_own_item(self):
        response = self.start(user=self.owner)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_start_about_unavailable_item(self):
        for item_status in ['draft', 'archived', 'reserved', 'given']:
            response = self.start(item=make_item(self.owner, status=item_status))
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, item_status)
        deleted = make_item(self.owner)
        deleted.deleted_at = deleted.created_at
        deleted.save()
        self.assertEqual(self.start(item=deleted).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.client.post(self.url, {'item_id': 9999}, format='json').status_code, 400)

    def test_only_participants_see_conversation(self):
        conversation_id = self.start().data['id']
        detail = f'{self.url}/{conversation_id}'
        self.client.force_authenticate(self.stranger)
        self.assertEqual(self.client.get(self.url).data, [])
        self.assertEqual(self.client.get(detail).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.get(f'{detail}/messages').status_code, status.HTTP_404_NOT_FOUND)
        response = self.client.post(f'{detail}/messages', {'body': 'Привет'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.get(detail).data['companion']['id'], self.requester.pk)

    def test_messages_flow(self):
        detail = f'{self.url}/{self.start().data["id"]}'
        response = self.client.post(f'{detail}/messages', {'body': '  Здравствуйте, вещь ещё актуальна?  '}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['body'], 'Здравствуйте, вещь ещё актуальна?')
        self.assertEqual(response.data['sender_id'], self.requester.pk)

        self.client.force_authenticate(self.owner)
        self.client.post(f'{detail}/messages', {'body': 'Да, актуальна'}, format='json')
        bodies = [message['body'] for message in self.client.get(f'{detail}/messages').data]
        self.assertEqual(bodies, ['Здравствуйте, вещь ещё актуальна?', 'Да, актуальна'])

    def test_invalid_message_body(self):
        detail = f'{self.url}/{self.start().data["id"]}'
        for body in ['', '   ', 'x' * (MAX_MESSAGE_LENGTH + 1)]:
            response = self.client.post(f'{detail}/messages', {'body': body}, format='json')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, len(body))

    def test_unread_count_and_mark_read(self):
        detail = f'{self.url}/{self.start().data["id"]}'
        for body in ['Первое', 'Второе']:
            self.client.post(f'{detail}/messages', {'body': body}, format='json')

        self.assertEqual(self.client.get(detail).data['unread_count'], 0)
        self.client.force_authenticate(self.owner)
        data = self.client.get(self.url).data[0]
        self.assertEqual(data['unread_count'], 2)
        self.assertEqual(data['last_message']['body'], 'Второе')

        self.assertEqual(self.client.post(f'{detail}/read').data, {'marked_read': 2})
        self.assertEqual(self.client.get(detail).data['unread_count'], 0)
        self.assertTrue(all(m['read_at'] for m in self.client.get(f'{detail}/messages').data))

        self.client.force_authenticate(self.requester)
        self.assertEqual(self.client.post(f'{detail}/read').data, {'marked_read': 0})

    def test_list_is_sorted_by_last_activity(self):
        first = self.start().data['id']
        second = self.start(item=make_item(self.owner, title='Книга')).data['id']
        self.client.post(f'{self.url}/{first}/messages', {'body': 'Свежее'}, format='json')
        self.assertEqual([c['id'] for c in self.client.get(self.url).data], [first, second])

    def test_item_cover_in_conversation(self):
        ItemPhoto.objects.create(item=self.item, image='items/cover.jpg', position=0)
        data = self.start().data
        self.assertTrue(data['item']['cover'].endswith('/media/items/cover.jpg'))

    def test_list_query_count_does_not_grow(self):
        for number in range(4):
            conversation_id = self.start(item=make_item(self.owner, title=f'Вещь {number}')).data['id']
            self.client.post(f'{self.url}/{conversation_id}/messages', {'body': 'Привет'}, format='json')
        with self.assertNumQueries(3):
            self.client.get(self.url)

    def test_works_with_cookie_login(self):
        client = APIClient()
        client.post('/api/v1/users/login', {'email': self.requester.email, 'password': 'Xk29-test-Qz'})
        response = client.post(self.url, {'item_id': self.item.pk}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


@override_settings(CHANNEL_LAYERS=IN_MEMORY_LAYER)
class ChatWebSocketTests(TransactionTestCase):
    serialized_rollback = True

    def setUp(self):
        self.owner, self.requester, self.stranger = make_users()
        self.conversation = Conversation.objects.create(
            item=make_item(self.owner), owner=self.owner, requester=self.requester
        )
        self.path = f'/ws/conversations/{self.conversation.pk}'
        self.sockets = []

    async def close_sockets(self):
        for socket in self.sockets:
            await socket.disconnect()

    def socket(self, user=None, origin='http://localhost:8000', path=None):
        headers = [(b'origin', origin.encode())]
        if user is not None:
            headers.append((b'cookie', f'access_token={AccessToken.for_user(user)}'.encode()))
        return WebsocketCommunicator(application, path or self.path, headers=headers)

    async def connected(self, user):
        socket = self.socket(user)
        accepted, _ = await socket.connect()
        self.assertTrue(accepted)
        self.sockets.append(socket)
        return socket

    async def closed_with(self, socket):
        accepted, _ = await socket.connect()
        self.assertTrue(accepted)
        output = await socket.receive_output(timeout=3)
        self.assertEqual(output['type'], 'websocket.close')
        return output['code']

    async def test_anonymous_is_closed_with_4401(self):
        self.assertEqual(await self.closed_with(self.socket()), 4401)

    async def test_invalid_token_is_closed_with_4401(self):
        socket = WebsocketCommunicator(application, self.path, headers=[
            (b'origin', b'http://localhost:8000'), (b'cookie', b'access_token=broken'),
        ])
        self.assertEqual(await self.closed_with(socket), 4401)

    async def test_stranger_is_closed_with_4403(self):
        self.assertEqual(await self.closed_with(self.socket(self.stranger)), 4403)
        missing = self.socket(self.owner, path='/ws/conversations/999999')
        self.assertEqual(await self.closed_with(missing), 4403)

    async def test_foreign_origin_is_rejected(self):
        accepted, _ = await self.socket(self.owner, origin='https://evil.example').connect()
        self.assertFalse(accepted)

    async def test_message_is_delivered_to_both_participants(self):
        owner, requester = await self.connected(self.owner), await self.connected(self.requester)
        await requester.send_json_to({'type': 'message', 'body': 'Здравствуйте!'})
        for socket in (owner, requester):
            event = await socket.receive_json_from(timeout=3)
            self.assertEqual(event['type'], 'message')
            self.assertEqual(event['message']['body'], 'Здравствуйте!')
            self.assertEqual(event['message']['sender_id'], self.requester.pk)
        count = await database_sync_to_async(Message.objects.filter(conversation=self.conversation).count)()
        self.assertEqual(count, 1)
        await self.close_sockets()

    async def test_message_sent_over_rest_is_pushed(self):
        owner = await self.connected(self.owner)

        def post():
            client = APIClient()
            client.force_authenticate(self.requester)
            return client.post(f'/api/v1/conversations/{self.conversation.pk}/messages', {'body': 'Через REST'},
                               format='json')

        response = await sync_to_async(post)()
        self.assertEqual(response.status_code, 201)
        event = await owner.receive_json_from(timeout=3)
        self.assertEqual(event['message']['body'], 'Через REST')
        await self.close_sockets()

    async def test_read_event(self):
        owner, requester = await self.connected(self.owner), await self.connected(self.requester)
        await requester.send_json_to({'type': 'message', 'body': 'Привет'})
        await owner.receive_json_from(timeout=3)
        await requester.receive_json_from(timeout=3)
        await owner.send_json_to({'type': 'read'})
        event = await requester.receive_json_from(timeout=3)
        self.assertEqual(event['type'], 'read')
        self.assertEqual(event['reader_id'], self.owner.pk)
        await self.close_sockets()

    async def test_invalid_payloads_return_errors(self):
        socket = await self.connected(self.owner)
        for payload in [{'type': 'message', 'body': ''}, {'type': 'unknown'}, ['not', 'an', 'object']]:
            await socket.send_json_to(payload)
            self.assertEqual((await socket.receive_json_from(timeout=3))['type'], 'error')
        await socket.send_to(text_data='not json')
        self.assertEqual((await socket.receive_json_from(timeout=3))['type'], 'error')
        self.assertTrue(await socket.receive_nothing(timeout=0.2))
        await self.close_sockets()

    async def test_stranger_does_not_receive_messages_of_other_conversation(self):
        other = await database_sync_to_async(Conversation.objects.create)(
            item=await database_sync_to_async(make_item)(self.owner, title='Другая'),
            owner=self.owner, requester=self.stranger,
        )
        stranger = self.socket(self.stranger, path=f'/ws/conversations/{other.pk}')
        await stranger.connect()
        self.sockets.append(stranger)
        requester = await self.connected(self.requester)
        await requester.send_json_to({'type': 'message', 'body': 'Только для владельца'})
        await requester.receive_json_from(timeout=3)
        await asyncio.sleep(0.1)
        self.assertTrue(await stranger.receive_nothing(timeout=0.3))
        await self.close_sockets()
