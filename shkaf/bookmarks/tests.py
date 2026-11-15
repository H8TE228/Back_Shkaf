from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APITestCase

from exchange_points.models import Address, ExchangePoint
from items.models import Item, ItemPhoto, ItemType

from .models import Bookmark


class BookmarkTestCase(APITestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            email='owner@example.test', username='owner', password='Xk29-test-Qz'
        )
        self.user = get_user_model().objects.create_user(
            email='user@example.test', username='user', password='Xk29-test-Qz'
        )
        self.item_type = ItemType.objects.get(title='Книги')
        self.item = Item.objects.create(
            owner=self.owner, item_type=self.item_type, title='Роман',
            condition='good', exchange_format='free', status='active',
        )
        self.point = ExchangePoint.objects.create(
            title='Добрый Шкаф', address=Address.objects.create(
                city='Екатеринбург', street='Мира', building='19', location=Point(60.65, 56.84, srid=4326)
            ),
        )
        self.point.item_types.set([self.item_type])
        self.item_url = f'/api/v1/items/{self.item.pk}/bookmark'
        self.point_url = f'/api/v1/exchangePoints/{self.point.pk}/bookmark'
        self.list_url = '/api/v1/me/bookmarks'
        self.client.force_authenticate(self.user)


class BookmarkModelTests(BookmarkTestCase):
    def test_exactly_one_target_is_required(self):
        for targets in ({}, {'item': self.item, 'point': self.point}):
            with self.assertRaises(IntegrityError), transaction.atomic():
                Bookmark.objects.create(user=self.user, **targets)

    def test_user_cannot_bookmark_same_target_twice(self):
        for targets in ({'item': self.item}, {'point': self.point}):
            Bookmark.objects.create(user=self.user, **targets)
            with self.assertRaises(IntegrityError), transaction.atomic():
                Bookmark.objects.create(user=self.user, **targets)

    def test_different_users_can_bookmark_same_target(self):
        for targets in ({'item': self.item}, {'point': self.point}):
            Bookmark.objects.create(user=self.user, **targets)
            Bookmark.objects.create(user=self.owner, **targets)
        self.assertEqual(Bookmark.objects.count(), 4)

    def test_hard_deleting_target_removes_its_bookmark(self):
        Bookmark.objects.create(user=self.user, item=self.item)
        Bookmark.objects.create(user=self.user, point=self.point)
        self.item.delete()
        self.point.delete()
        self.assertFalse(Bookmark.objects.exists())


class BookmarkApiTests(BookmarkTestCase):
    def test_all_endpoints_require_authentication(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.list_url).status_code, 401)
        for url in (self.item_url, self.point_url):
            self.assertEqual(self.client.post(url).status_code, 401)
            self.assertEqual(self.client.delete(url).status_code, 401)

    def test_post_and_delete_are_idempotent(self):
        for url in (self.item_url, self.point_url):
            response = self.client.post(url)
            self.assertEqual(response.status_code, 201, response.data)
            first_id = response.data['id']
            created_at = response.data['created_at']
            response = self.client.post(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['id'], first_id)
            self.assertEqual(response.data['created_at'], created_at)
            self.assertEqual(Bookmark.objects.filter(pk=first_id, user=self.user).count(), 1)
            self.assertEqual(self.client.delete(url).status_code, 204)
            self.assertEqual(self.client.delete(url).status_code, 204)
            self.assertFalse(Bookmark.objects.filter(pk=first_id).exists())

    def test_list_contains_nested_cards_newest_first(self):
        first = self.client.post(self.item_url).data
        second = self.client.post(self.point_url).data
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([bookmark['id'] for bookmark in response.data], [second['id'], first['id']])
        self.assertEqual(set(response.data[0]), {'id', 'created_at', 'item', 'point'})
        self.assertIsNone(response.data[0]['item'])
        self.assertEqual(response.data[0]['point']['id'], self.point.pk)
        self.assertEqual(response.data[0]['point']['address']['city'], 'Екатеринбург')
        self.assertEqual(response.data[0]['point']['item_types'][0]['id'], self.item_type.pk)
        self.assertIsNone(response.data[1]['point'])
        self.assertEqual(response.data[1]['item']['id'], self.item.pk)
        self.assertEqual(response.data[1]['item']['item_type_title'], 'Книги')

    def test_filter_by_type(self):
        self.client.post(self.item_url)
        self.client.post(self.point_url)
        for target_type in ('item', 'point'):
            response = self.client.get(self.list_url, {'type': target_type})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.data), 1)
            self.assertIsNotNone(response.data[0][target_type])
        self.assertEqual(self.client.get(self.list_url, {'type': 'unknown'}).status_code, 400)

    def test_only_current_users_bookmarks_are_visible_or_removed(self):
        other_item = Bookmark.objects.create(user=self.owner, item=self.item)
        other_point = Bookmark.objects.create(user=self.owner, point=self.point)
        self.assertEqual(self.client.get(self.list_url).data, [])
        self.client.delete(self.item_url)
        self.client.delete(self.point_url)
        self.assertEqual(Bookmark.objects.count(), 2)
        response = self.client.post(self.item_url, {'user_id': self.owner.pk}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Bookmark.objects.get(pk=response.data['id']).user, self.user)
        self.assertNotEqual(response.data['id'], other_item.pk)
        self.assertTrue(Bookmark.objects.filter(pk=other_point.pk).exists())

    def test_only_supported_methods_are_allowed(self):
        self.assertEqual(self.client.post(self.list_url).status_code, 405)
        for url in (self.item_url, self.point_url):
            self.assertEqual(self.client.get(url).status_code, 405)
            self.assertEqual(self.client.patch(url, {}, format='json').status_code, 405)

    def test_missing_target_returns_404_on_post_but_delete_succeeds(self):
        for url in ('/api/v1/items/99999/bookmark', '/api/v1/exchangePoints/99999/bookmark'):
            self.assertEqual(self.client.post(url).status_code, 404)
            self.assertEqual(self.client.delete(url).status_code, 204)

    def test_visible_public_item_statuses_can_be_bookmarked(self):
        for item_status in ('active', 'reserved', 'given'):
            self.item.status = item_status
            self.item.save()
            self.assertIn(self.client.post(self.item_url).status_code, (200, 201))
            self.assertEqual(len(self.client.get(self.list_url).data), 1)

    def test_foreign_drafts_and_archived_items_are_hidden(self):
        Bookmark.objects.create(user=self.user, item=self.item)
        for item_status in ('draft', 'archived'):
            self.item.status = item_status
            self.item.save()
            self.assertEqual(self.client.post(self.item_url).status_code, 404)
            self.assertEqual(self.client.get(self.list_url).data, [])
        self.assertEqual(self.client.delete(self.item_url).status_code, 204)
        self.assertFalse(Bookmark.objects.exists())

    def test_owner_can_bookmark_own_drafts_and_archived_items(self):
        self.client.force_authenticate(self.owner)
        for item_status in ('draft', 'archived'):
            self.item.status = item_status
            self.item.save()
            self.assertIn(self.client.post(self.item_url).status_code, (200, 201))
            self.assertEqual(len(self.client.get(self.list_url).data), 1)

    def test_soft_deleted_item_is_hidden_but_bookmark_can_be_removed(self):
        self.client.post(self.item_url)
        self.item.deleted_at = timezone.now()
        self.item.save()
        self.assertEqual(self.client.get(self.list_url).data, [])
        self.assertEqual(self.client.post(self.item_url).status_code, 404)
        self.assertEqual(self.client.delete(self.item_url).status_code, 204)
        self.assertFalse(Bookmark.objects.exists())

    def test_items_of_deleted_owner_are_hidden(self):
        self.client.post(self.item_url)
        self.owner.anonymize()
        self.assertEqual(self.client.get(self.list_url).data, [])
        self.assertEqual(self.client.post(self.item_url).status_code, 404)
        self.assertEqual(self.client.delete(self.item_url).status_code, 204)

    def test_points_in_all_statuses_can_be_bookmarked(self):
        for point_status in ('active', 'needs_check', 'closed'):
            self.point.status = point_status
            self.point.save()
            self.assertIn(self.client.post(self.point_url).status_code, (200, 201))
            self.assertEqual(len(self.client.get(self.list_url).data), 1)

    def test_list_query_count_does_not_grow(self):
        for number in range(5):
            item = Item.objects.create(
                owner=self.owner, item_type=self.item_type, title=f'Книга {number}',
                condition='good', exchange_format='free', status='active',
            )
            ItemPhoto.objects.create(item=item, image='items/a.jpg')
            Bookmark.objects.create(user=self.user, item=item)
            point = ExchangePoint.objects.create(
                title=f'Пункт {number}', address=Address.objects.create(
                    city='Екатеринбург', street='Мира', building=str(number),
                    location=Point(60.65, 56.84, srid=4326),
                ),
            )
            point.item_types.set([self.item_type])
            Bookmark.objects.create(user=self.user, point=point)
        with self.assertNumQueries(3):
            response = self.client.get(self.list_url)
        self.assertEqual(len(response.data), 10)
