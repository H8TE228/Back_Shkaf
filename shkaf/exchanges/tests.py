from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from items.models import Item, ItemType

from .models import Exchange

User = get_user_model()


def make_users():
    return [
        User.objects.create_user(email=f'{name}@example.test', username=name, password='Xk29-test-Qz')
        for name in ('giver', 'receiver', 'second', 'stranger')
    ]


def make_item(owner, **kwargs):
    item_type, _ = ItemType.objects.get_or_create(title='Обувь')
    defaults = {'title': 'Кроссовки', 'condition': 'good', 'exchange_format': 'free', 'status': 'active'}
    return Item.objects.create(owner=owner, item_type=item_type, **{**defaults, **kwargs})


class ExchangeConstraintTests(TestCase):
    def setUp(self):
        self.giver, self.receiver, self.second, _ = make_users()
        self.item = make_item(self.giver)

    def test_only_one_agreed_or_completed_exchange_per_item(self):
        Exchange.objects.create(item=self.item, giver=self.giver, receiver=self.receiver, status='agreed')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Exchange.objects.create(item=self.item, giver=self.giver, receiver=self.second, status='agreed')

    def test_only_one_open_request_per_receiver(self):
        Exchange.objects.create(item=self.item, giver=self.giver, receiver=self.receiver)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Exchange.objects.create(item=self.item, giver=self.giver, receiver=self.receiver)
        Exchange.objects.filter(receiver=self.receiver).update(status='cancelled')
        Exchange.objects.create(item=self.item, giver=self.giver, receiver=self.receiver)

    def test_giver_cannot_be_receiver(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Exchange.objects.create(item=self.item, giver=self.giver, receiver=self.giver)


class ExchangeApiTestCase(APITestCase):
    def setUp(self):
        self.giver, self.receiver, self.second, self.stranger = make_users()
        self.item = make_item(self.giver)
        self.item_url = f'/api/v1/items/{self.item.pk}/exchanges'

    def as_user(self, user):
        self.client.force_authenticate(user)

    def request_item(self, user=None):
        self.as_user(user or self.receiver)
        return self.client.post(self.item_url)

    def act(self, user, exchange_id, name):
        self.as_user(user)
        return self.client.post(f'/api/v1/exchanges/{exchange_id}/{name}')

    def item_status(self):
        self.item.refresh_from_db()
        return self.item.status


class ExchangeRequestTests(ExchangeApiTestCase):
    def test_request_requires_auth(self):
        self.assertEqual(self.client.post(self.item_url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_request(self):
        response = self.request_item()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['status'], 'requested')
        self.assertEqual(response.data['giver_id'], self.giver.pk)
        self.assertEqual(response.data['receiver_id'], self.receiver.pk)
        self.assertEqual(response.data['item']['id'], self.item.pk)

    def test_cannot_request_own_item(self):
        self.assertEqual(self.request_item(self.giver).status_code, status.HTTP_400_BAD_REQUEST)

    def test_second_open_request_is_conflict(self):
        self.request_item()
        self.assertEqual(self.request_item().status_code, status.HTTP_409_CONFLICT)

    def test_unavailable_items(self):
        for item_status, expected in [('reserved', 409), ('given', 409), ('draft', 404), ('archived', 404)]:
            item = make_item(self.giver, status=item_status)
            self.as_user(self.receiver)
            response = self.client.post(f'/api/v1/items/{item.pk}/exchanges')
            self.assertEqual(response.status_code, expected, item_status)

    def test_owner_sees_all_requests_others_only_own(self):
        self.request_item(self.receiver)
        self.request_item(self.second)
        self.as_user(self.giver)
        self.assertEqual(len(self.client.get(self.item_url).data['results']), 2)
        self.as_user(self.second)
        data = self.client.get(self.item_url).data['results']
        self.assertEqual([e['receiver_id'] for e in data], [self.second.pk])
        self.as_user(self.stranger)
        self.assertEqual(self.client.get(self.item_url).data['results'], [])


class ExchangeFlowTests(ExchangeApiTestCase):
    def setUp(self):
        super().setUp()
        self.exchange_id = self.request_item().data['id']

    def test_full_cycle(self):
        response = self.act(self.giver, self.exchange_id, 'agree')
        self.assertEqual(response.data['status'], 'agreed')
        self.assertEqual(self.item_status(), 'reserved')

        response = self.act(self.receiver, self.exchange_id, 'confirm')
        self.assertEqual(response.data['status'], 'agreed')
        self.assertIsNotNone(response.data['receiver_confirmed_at'])

        response = self.act(self.giver, self.exchange_id, 'confirm')
        self.assertEqual(response.data['status'], 'completed')
        self.assertIsNotNone(response.data['completed_at'])
        self.assertEqual(self.item_status(), 'given')

    def test_double_reserve_is_prevented(self):
        second_id = self.request_item(self.second).data['id']
        self.assertEqual(self.act(self.giver, self.exchange_id, 'agree').status_code, 200)
        response = self.act(self.giver, second_id, 'agree')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(Exchange.objects.get(pk=second_id).status, 'requested')

    def test_completion_declines_other_requests(self):
        second_id = self.request_item(self.second).data['id']
        self.act(self.giver, self.exchange_id, 'agree')
        self.act(self.giver, self.exchange_id, 'confirm')
        self.act(self.receiver, self.exchange_id, 'confirm')
        self.assertEqual(Exchange.objects.get(pk=second_id).status, 'declined')

    def test_only_giver_can_agree_or_decline(self):
        for user in (self.receiver, self.stranger):
            for name in ('agree', 'decline'):
                self.assertIn(self.act(user, self.exchange_id, name).status_code, (403, 404), (user, name))
        self.assertEqual(Exchange.objects.get(pk=self.exchange_id).status, 'requested')

    def test_decline(self):
        self.assertEqual(self.act(self.giver, self.exchange_id, 'decline').data['status'], 'declined')
        self.assertEqual(self.act(self.giver, self.exchange_id, 'agree').status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(self.item_status(), 'active')

    def test_receiver_withdraws_request(self):
        self.assertEqual(self.act(self.giver, self.exchange_id, 'cancel').status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.act(self.receiver, self.exchange_id, 'cancel').data['status'], 'cancelled')
        self.assertEqual(self.request_item().status_code, status.HTTP_201_CREATED)

    def test_cancel_agreed_returns_item_to_catalog(self):
        self.act(self.giver, self.exchange_id, 'agree')
        self.assertEqual(self.act(self.giver, self.exchange_id, 'cancel').data['status'], 'cancelled')
        self.assertEqual(self.item_status(), 'active')
        second_id = self.request_item(self.second).data['id']
        self.assertEqual(self.act(self.giver, second_id, 'agree').status_code, 200)

    def test_confirm_requires_agreed(self):
        self.assertEqual(self.act(self.receiver, self.exchange_id, 'confirm').status_code, status.HTTP_409_CONFLICT)

    def test_completed_exchange_is_final(self):
        self.act(self.giver, self.exchange_id, 'agree')
        self.act(self.giver, self.exchange_id, 'confirm')
        self.act(self.receiver, self.exchange_id, 'confirm')
        for user, name in [(self.giver, 'cancel'), (self.receiver, 'cancel'), (self.giver, 'decline')]:
            self.assertEqual(self.act(user, self.exchange_id, name).status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(self.item_status(), 'given')

    def test_repeated_confirm_keeps_first_time(self):
        self.act(self.giver, self.exchange_id, 'agree')
        first = self.act(self.receiver, self.exchange_id, 'confirm').data['receiver_confirmed_at']
        second = self.act(self.receiver, self.exchange_id, 'confirm').data['receiver_confirmed_at']
        self.assertEqual(first, second)

    def test_reserved_item_cannot_be_edited_by_owner(self):
        self.act(self.giver, self.exchange_id, 'agree')
        self.as_user(self.giver)
        response = self.client.patch(f'/api/v1/items/{self.item.pk}', {'status': 'archived'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_archiving_or_deleting_item_declines_requests(self):
        self.as_user(self.giver)
        self.client.patch(f'/api/v1/items/{self.item.pk}', {'status': 'archived'}, format='json')
        self.assertEqual(Exchange.objects.get(pk=self.exchange_id).status, 'declined')

        item = make_item(self.giver, title='Вторая')
        self.as_user(self.receiver)
        exchange_id = self.client.post(f'/api/v1/items/{item.pk}/exchanges').data['id']
        self.as_user(self.giver)
        self.client.delete(f'/api/v1/items/{item.pk}')
        self.assertEqual(Exchange.objects.get(pk=exchange_id).status, 'declined')

    def test_stranger_cannot_see_or_act(self):
        self.as_user(self.stranger)
        self.assertEqual(self.client.get(f'/api/v1/exchanges/{self.exchange_id}').status_code, 404)
        self.assertEqual(self.act(self.stranger, self.exchange_id, 'confirm').status_code, 404)

    def test_my_exchanges_with_role_filter(self):
        self.as_user(self.receiver)
        self.assertEqual(len(self.client.get('/api/v1/exchanges', {'role': 'receiver'}).data['results']), 1)
        self.assertEqual(self.client.get('/api/v1/exchanges', {'role': 'giver'}).data['results'], [])
        self.as_user(self.giver)
        self.assertEqual(
            len(self.client.get('/api/v1/exchanges', {'role': 'giver', 'status': 'requested'}).data['results']), 1,
        )
        self.assertEqual(self.client.get('/api/v1/exchanges', {'role': 'x'}).status_code, 400)


class ExchangeAdminTests(TestCase):
    def test_admin_list_opens(self):
        admin = User.objects.create_superuser(email='admin@example.test', username='admin', password='Xk29-test-Qz')
        self.client.force_login(admin)
        self.assertEqual(self.client.get(reverse('admin:exchanges_exchange_changelist')).status_code, 200)
