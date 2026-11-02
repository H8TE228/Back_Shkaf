from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse

from .models import Item, ItemPhoto, ItemType

User = get_user_model()


class ItemModelTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email='owner@example.test', username='owner', password='Xk29-test-Qz'
        )
        self.item_type = ItemType.objects.create(title='Детская одежда')
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
