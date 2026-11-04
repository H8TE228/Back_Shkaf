import io
import shutil
import tempfile
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Item, ItemPhoto, ItemType

User = get_user_model()


class ItemModelTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email='owner@example.test', username='owner', password='Xk29-test-Qz'
        )
        self.item_type = ItemType.objects.get(title='Детская одежда')
        self.item = Item.objects.create(
            owner=self.owner,
            item_type=self.item_type,
            title='Куртка',
            condition=Item.Condition.GOOD,
            exchange_format=Item.ExchangeFormat.FREE,
        )

    def test_new_item_is_draft(self):
        self.assertEqual(self.item.status, Item.Status.DRAFT)

    def test_item_type_title_is_unique(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ItemType.objects.create(title='Детская одежда')

    def test_used_item_type_and_owner_are_protected(self):
        with self.assertRaises(ProtectedError):
            self.item_type.delete()
        with self.assertRaises(ProtectedError):
            self.owner.delete()

    def test_approx_location_is_rounded(self):
        self.item.approx_location = Point(60.60571, 56.83892, srid=4326)
        self.item.save()
        self.item.refresh_from_db()
        self.assertAlmostEqual(self.item.approx_location.x, 60.605)
        self.assertAlmostEqual(self.item.approx_location.y, 56.84)

    def test_photo_position_is_unique_within_item(self):
        ItemPhoto.objects.create(item=self.item, image='items/a.jpg', position=0)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ItemPhoto.objects.create(item=self.item, image='items/b.jpg', position=0)

    def test_photos_are_deleted_with_item(self):
        ItemPhoto.objects.create(item=self.item, image='items/a.jpg', position=0)
        self.item.delete()
        self.assertFalse(ItemPhoto.objects.exists())


class AdminPagesTests(TestCase):
    def setUp(self):
        admin = User.objects.create_superuser(
            email='admin@example.test', username='admin', password='Xk29-test-Qz'
        )
        self.client.force_login(admin)

    def test_list_and_add_pages_open(self):
        for model in ['items_item', 'items_itemtype', 'exchange_points_address', 'users_user']:
            for page in ['changelist', 'add']:
                response = self.client.get(reverse(f'admin:{model}_{page}'))
                self.assertEqual(response.status_code, 200, f'{model} {page}')


def image_file(name='photo.jpg', image_format='JPEG'):
    buffer = io.BytesIO()
    Image.new('RGB', (10, 10), 'white').save(buffer, image_format)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type=f'image/{image_format.lower()}')


class ItemApiTestCase(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email='owner@example.test', username='owner', password='Xk29-test-Qz')
        self.other = User.objects.create_user(email='other@example.test', username='other', password='Xk29-test-Qz')
        self.item_type = ItemType.objects.get(title='Обувь')

    def make_item(self, **kwargs):
        defaults = {
            'owner': self.owner,
            'item_type': self.item_type,
            'title': 'Кроссовки',
            'condition': Item.Condition.GOOD,
            'exchange_format': Item.ExchangeFormat.FREE,
            'status': Item.Status.ACTIVE,
        }
        return Item.objects.create(**{**defaults, **kwargs})

    def payload(self, **kwargs):
        return {
            'item_type': self.item_type.pk,
            'title': 'Кроссовки',
            'description': 'Почти новые',
            'condition': 'good',
            'exchange_format': 'free',
            **kwargs,
        }


class ItemTypeApiTests(ItemApiTestCase):
    def test_types_from_terms_of_reference_are_seeded(self):
        response = self.client.get('/api/v1/itemTypes')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {item_type['title'] for item_type in response.data},
            {'Детская одежда', 'Взрослая одежда', 'Обувь', 'Игрушки', 'Книги', 'Мебель'},
        )

    def test_types_are_read_only(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post('/api/v1/itemTypes', {'title': 'Новый тип'})
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class ItemReadTests(ItemApiTestCase):
    def setUp(self):
        super().setUp()
        self.active = self.make_item(title='Активная')
        self.draft = self.make_item(title='Черновик', status=Item.Status.DRAFT)
        self.archived = self.make_item(title='Архив', status=Item.Status.ARCHIVED)
        self.reserved = self.make_item(title='Резерв', status=Item.Status.RESERVED)

    def titles(self, url='/api/v1/items', **params):
        return {item['title'] for item in self.client.get(url, params).data}

    def test_list_shows_only_active_by_default(self):
        self.assertEqual(self.titles(), {'Активная'})

    def test_response_fields(self):
        data = self.client.get(f'/api/v1/items/{self.active.pk}').data
        self.assertEqual(data['owner_id'], self.owner.pk)
        self.assertEqual(data['item_type'], self.item_type.pk)
        self.assertEqual(data['item_type_title'], 'Обувь')
        self.assertEqual(data['photos'], [])

    def test_status_filter_respects_visibility(self):
        self.assertEqual(self.titles(status='reserved'), {'Резерв'})
        self.assertEqual(self.titles(status='draft'), set())
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.titles(status='draft'), {'Черновик'})
        self.client.force_authenticate(self.other)
        self.assertEqual(self.titles(status='draft'), set())

    def test_draft_detail_is_visible_to_owner_only(self):
        url = f'/api/v1/items/{self.draft.pk}'
        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.get(url).status_code, status.HTTP_200_OK)

    def test_filters_and_search(self):
        books = ItemType.objects.get(title='Книги')
        self.make_item(title='Роман', description='Классика', item_type=books, exchange_format='swap', district='Кировский')
        self.assertEqual(self.titles(item_type=books.pk), {'Роман'})
        self.assertEqual(self.titles(exchange_format='swap'), {'Роман'})
        self.assertEqual(self.titles(district='Кировский'), {'Роман'})
        self.assertEqual(self.titles(search='классика'), {'Роман'})
        self.assertEqual(self.titles(search='активная'), {'Активная'})

    def test_invalid_filter_value(self):
        response = self.client.get('/api/v1/items', {'exchange_format': 'unknown'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_ordering(self):
        self.make_item(title='Новая')
        titles = [item['title'] for item in self.client.get('/api/v1/items', {'ordering': 'created_at'}).data]
        self.assertEqual(titles, ['Активная', 'Новая'])
        titles = [item['title'] for item in self.client.get('/api/v1/items').data]
        self.assertEqual(titles, ['Новая', 'Активная'])

    def test_list_query_count_does_not_grow(self):
        for number in range(5):
            ItemPhoto.objects.create(item=self.make_item(), image='items/a.jpg', position=number)
        with self.assertNumQueries(2):
            self.client.get('/api/v1/items')

    def test_items_of_deleted_user_are_hidden(self):
        self.owner.anonymize()
        self.assertEqual(self.titles(), set())
        response = self.client.get(f'/api/v1/items/{self.active.pk}')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_my_items_include_all_own_statuses(self):
        self.make_item(title='Чужая', owner=self.other)
        deleted = self.make_item(title='Удалённая')
        deleted.deleted_at = deleted.created_at
        deleted.save()
        self.assertEqual(self.client.get('/api/v1/me/items').status_code, status.HTTP_401_UNAUTHORIZED)
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.titles('/api/v1/me/items'), {'Активная', 'Черновик', 'Архив', 'Резерв'})
        self.assertEqual(self.titles('/api/v1/me/items', status='draft'), {'Черновик'})


class ItemWriteTests(ItemApiTestCase):
    def test_create_requires_auth(self):
        response = self.client.post('/api/v1/items', self.payload())
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_takes_owner_from_token(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post('/api/v1/items', self.payload(owner=self.other.pk, owner_id=self.other.pk))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['owner_id'], self.owner.pk)
        self.assertEqual(response.data['status'], 'draft')

    def test_create_with_cookie_login(self):
        self.client.post('/api/v1/users/login', {'email': self.owner.email, 'password': 'Xk29-test-Qz'})
        response = self.client.post('/api/v1/items', self.payload(status='active'))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_validates_fields(self):
        self.client.force_authenticate(self.owner)
        for field, value in [('exchange_format', 'charity'), ('condition', 'bad'), ('item_type', 9999), ('title', '')]:
            response = self.client.post('/api/v1/items', self.payload(**{field: value}))
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, field)
            self.assertIn(field, response.data)

    def test_cannot_create_reserved_or_given(self):
        self.client.force_authenticate(self.owner)
        for value in ['reserved', 'given', 'archived']:
            response = self.client.post('/api/v1/items', self.payload(status=value))
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, value)

    def test_owner_can_update_with_patch_and_put(self):
        item = self.make_item()
        self.client.force_authenticate(self.owner)
        url = f'/api/v1/items/{item.pk}'
        self.assertEqual(self.client.patch(url, {'title': 'Новое'}).data['title'], 'Новое')
        self.assertEqual(self.client.put(url, self.payload(title='Ещё новее')).data['title'], 'Ещё новее')

    def test_other_user_cannot_change_or_delete(self):
        item = self.make_item()
        self.client.force_authenticate(self.other)
        url = f'/api/v1/items/{item.pk}'
        self.assertEqual(self.client.patch(url, {'title': 'X'}).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_cannot_change_or_delete(self):
        url = f'/api/v1/items/{self.make_item().pk}'
        self.assertEqual(self.client.patch(url, {'title': 'X'}).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_allowed_status_transitions(self):
        item = self.make_item(status=Item.Status.DRAFT)
        self.client.force_authenticate(self.owner)
        url = f'/api/v1/items/{item.pk}'
        self.assertEqual(self.client.patch(url, {'status': 'active'}).data['status'], 'active')
        self.assertEqual(self.client.patch(url, {'status': 'archived'}).data['status'], 'archived')

    def test_forbidden_status_transitions(self):
        self.client.force_authenticate(self.owner)
        for current, target in [('draft', 'given'), ('draft', 'archived'), ('active', 'reserved'),
                                ('active', 'given'), ('active', 'draft'), ('archived', 'active')]:
            item = self.make_item(status=current)
            response = self.client.patch(f'/api/v1/items/{item.pk}', {'status': target})
            self.assertEqual(response.status_code, status.HTTP_409_CONFLICT, f'{current} -> {target}')

    def test_reserved_and_given_items_are_locked(self):
        self.client.force_authenticate(self.owner)
        for current in ['reserved', 'given']:
            url = f'/api/v1/items/{self.make_item(status=current).pk}'
            self.assertEqual(self.client.patch(url, {'title': 'X'}).status_code, status.HTTP_409_CONFLICT)
            self.assertEqual(self.client.delete(url).status_code, status.HTTP_409_CONFLICT)
            response = self.client.post(f'{url}/photos', {'image': image_file()}, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_delete_is_soft(self):
        item = self.make_item()
        self.client.force_authenticate(self.owner)
        url = f'/api/v1/items/{item.pk}'
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_404_NOT_FOUND)
        item.refresh_from_db()
        self.assertIsNotNone(item.deleted_at)


class ItemPhotoApiTests(ItemApiTestCase):
    def setUp(self):
        super().setUp()
        media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media_root, ignore_errors=True)
        settings_override = override_settings(MEDIA_ROOT=media_root)
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        self.item = self.make_item()
        self.url = f'/api/v1/items/{self.item.pk}/photos'
        self.client.force_authenticate(self.owner)

    def upload(self, file=None, url=None):
        return self.client.post(url or self.url, {'image': file or image_file()}, format='multipart')

    def test_upload_assigns_positions(self):
        first, second = self.upload(), self.upload(image_file('b.png', 'PNG'))
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual((first.data['position'], second.data['position']), (0, 1))
        photos = self.client.get(f'/api/v1/items/{self.item.pk}').data['photos']
        self.assertEqual([photo['id'] for photo in photos], [first.data['id'], second.data['id']])
        self.assertTrue(photos[0]['image'].startswith('http://testserver/media/items/'))

    def test_webp_is_accepted(self):
        self.assertEqual(self.upload(image_file('a.webp', 'WEBP')).status_code, status.HTTP_201_CREATED)

    def test_file_name_does_not_keep_original(self):
        response = self.upload(image_file('личный_документ.JPG'))
        self.assertNotIn('документ', response.data['image'])
        self.assertTrue(response.data['image'].endswith('.jpg'))

    def test_not_an_image_is_rejected(self):
        fake = SimpleUploadedFile('virus.jpg', b'not an image', content_type='image/jpeg')
        response = self.upload(fake)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(self.item.photos.exists())

    def test_disallowed_format_is_rejected(self):
        response = self.upload(image_file('a.gif', 'GIF'))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @mock.patch('items.serializers.MAX_PHOTO_SIZE', 10)
    def test_too_large_photo_is_rejected(self):
        self.assertEqual(self.upload().status_code, status.HTTP_400_BAD_REQUEST)

    def test_photo_limit(self):
        for _ in range(10):
            self.assertEqual(self.upload().status_code, status.HTTP_201_CREATED)
        response = self.upload()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.item.photos.count(), 10)

    def test_only_owner_can_upload_and_delete(self):
        photo_id = self.upload().data['id']
        self.client.force_authenticate(self.other)
        self.assertEqual(self.upload().status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.delete(f'{self.url}/{photo_id}').status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(None)
        self.assertEqual(self.upload().status_code, status.HTTP_401_UNAUTHORIZED)

    def test_delete_removes_file(self):
        photo_id = self.upload().data['id']
        name = self.item.photos.get(pk=photo_id).image.name
        self.assertTrue(default_storage.exists(name))
        self.assertEqual(self.client.delete(f'{self.url}/{photo_id}').status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(default_storage.exists(name))
        self.assertEqual(self.client.delete(f'{self.url}/{photo_id}').status_code, status.HTTP_404_NOT_FOUND)

    def test_position_is_not_reused_after_delete(self):
        first, second = self.upload(), self.upload()
        self.client.delete(f'{self.url}/{first.data["id"]}')
        self.assertEqual(self.upload().data['position'], second.data['position'] + 1)

    def test_photo_of_other_item_cannot_be_deleted(self):
        other_item = self.make_item()
        photo_id = self.upload().data['id']
        response = self.client.delete(f'/api/v1/items/{other_item.pk}/photos/{photo_id}')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(self.item.photos.filter(pk=photo_id).exists())
