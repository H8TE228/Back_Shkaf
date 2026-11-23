from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from exchanges.models import Exchange
from items.models import Item, ItemType

from .models import Review

User = get_user_model()


def make_users():
    return [
        User.objects.create_user(email=f'{name}@example.test', username=name, password='Xk29-test-Qz')
        for name in ('giver', 'receiver', 'stranger')
    ]


def make_exchange(giver, receiver, exchange_status='completed', title='Кроссовки'):
    item_type, _ = ItemType.objects.get_or_create(title='Обувь')
    item = Item.objects.create(owner=giver, item_type=item_type, title=title, condition='good',
                               exchange_format='free', status='given')
    return Exchange.objects.create(item=item, giver=giver, receiver=receiver, status=exchange_status)


class ReviewConstraintTests(TestCase):
    def setUp(self):
        self.giver, self.receiver, _ = make_users()
        self.exchange = make_exchange(self.giver, self.receiver)

    def test_rating_range_in_database(self):
        for rating in (0, 6):
            with self.assertRaises(IntegrityError), transaction.atomic():
                Review.objects.create(exchange=self.exchange, author=self.receiver, target_user=self.giver,
                                      rating=rating)

    def test_cannot_review_self(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Review.objects.create(exchange=self.exchange, author=self.giver, target_user=self.giver, rating=5)


class ReviewApiTests(APITestCase):
    url = '/api/v1/reviews'

    def setUp(self):
        self.giver, self.receiver, self.stranger = make_users()
        self.exchange = make_exchange(self.giver, self.receiver)

    def review(self, user, exchange=None, **data):
        self.client.force_authenticate(user)
        payload = {'exchange_id': (exchange or self.exchange).pk, 'rating': 5, 'comment': 'Всё отлично', **data}
        return self.client.post(self.url, payload, format='json')

    def test_requires_auth(self):
        response = self.client.post(self.url, {'exchange_id': self.exchange.pk, 'rating': 5}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_both_participants_review_each_other(self):
        response = self.review(self.receiver)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['target_user_id'], self.giver.pk)
        self.assertEqual(response.data['author']['id'], self.receiver.pk)
        self.assertEqual(response.data['item']['title'], 'Кроссовки')
        response = self.review(self.giver, rating=4)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['target_user_id'], self.receiver.pk)

    def test_only_one_review_per_exchange_from_author(self):
        self.review(self.receiver)
        self.assertEqual(self.review(self.receiver).status_code, status.HTTP_409_CONFLICT)

    def test_only_completed_exchange(self):
        for exchange_status in ('requested', 'agreed', 'declined', 'cancelled'):
            exchange = make_exchange(self.giver, self.receiver, exchange_status, title=exchange_status)
            response = self.review(self.receiver, exchange)
            self.assertEqual(response.status_code, status.HTTP_409_CONFLICT, exchange_status)

    def test_stranger_cannot_review(self):
        response = self.review(self.stranger)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('exchange_id', response.data)

    def test_rating_and_comment_validation(self):
        for data in ({'rating': 0}, {'rating': 6}, {'rating': 'abc'}, {'comment': 'x' * 2001}):
            response = self.review(self.receiver, **data)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, data)

    def test_author_can_edit_and_delete(self):
        review_id = self.review(self.receiver).data['id']
        detail = f'{self.url}/{review_id}'
        response = self.client.patch(detail, {'rating': 3, 'comment': 'Поправил'}, format='json')
        self.assertEqual(response.data['rating'], 3)
        other = make_exchange(self.giver, self.receiver, title='Другая')
        self.client.patch(detail, {'exchange_id': other.pk}, format='json')
        self.assertEqual(Review.objects.get(pk=review_id).exchange_id, self.exchange.pk)
        self.assertEqual(self.client.put(detail, {'rating': 2}, format='json').status_code, 405)
        self.assertEqual(self.client.delete(detail).status_code, status.HTTP_204_NO_CONTENT)

    def test_others_cannot_edit_or_delete(self):
        detail = f'{self.url}/{self.review(self.receiver).data["id"]}'
        for user in (self.giver, self.stranger):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.patch(detail, {'rating': 1}, format='json').status_code, 403)
            self.assertEqual(self.client.delete(detail).status_code, 403)

    def test_reviews_are_public_and_filterable(self):
        self.review(self.receiver)
        self.review(self.giver, rating=4)
        self.client.force_authenticate(None)
        self.assertEqual(len(self.client.get(self.url).data['results']), 2)
        about_giver = self.client.get(self.url, {'target_user': self.giver.pk}).data['results']
        self.assertEqual([r['author']['id'] for r in about_giver], [self.receiver.pk])
        by_giver = self.client.get(self.url, {'author': self.giver.pk}).data['results']
        self.assertEqual([r['rating'] for r in by_giver], [4])

    def test_rating_summary(self):
        url = f'/api/v1/users/{self.giver.pk}/rating'
        self.assertEqual(self.client.get(url).data, {'user_id': self.giver.pk, 'average': None, 'count': 0})
        self.review(self.receiver, rating=5)
        second = make_exchange(self.giver, self.stranger, title='Вторая')
        self.review(self.stranger, second, rating=4)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(url).data, {'user_id': self.giver.pk, 'average': 4.5, 'count': 2})
        self.assertEqual(self.client.get('/api/v1/users/99999/rating').status_code, 404)

    def test_list_query_count_does_not_grow(self):
        for number in range(4):
            exchange = make_exchange(self.giver, self.receiver, title=f'Вещь {number}')
            self.review(self.receiver, exchange)
        self.client.force_authenticate(None)
        with self.assertNumQueries(3):
            self.client.get(self.url)


class ReviewAdminTests(TestCase):
    def test_admin_list_opens(self):
        admin = User.objects.create_superuser(email='admin@example.test', username='admin', password='Xk29-test-Qz')
        self.client.force_login(admin)
        self.assertEqual(self.client.get(reverse('admin:reviews_review_changelist')).status_code, 200)
