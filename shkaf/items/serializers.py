from rest_framework import serializers

from .exceptions import StateConflict
from .models import Item, ItemPhoto, ItemType

MAX_PHOTO_SIZE = 5 * 1024 * 1024
ALLOWED_PHOTO_FORMATS = {'JPEG', 'PNG', 'WEBP'}
CREATE_STATUSES = {Item.Status.DRAFT, Item.Status.ACTIVE}
# Статусы reserved и given меняются только через передачу вещи (задача 2.23)
OWNER_TRANSITIONS = {
    Item.Status.DRAFT: {Item.Status.ACTIVE},
    Item.Status.ACTIVE: {Item.Status.ARCHIVED},
}


class ItemTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemType
        fields = ('id', 'title', 'description')


class ItemPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemPhoto
        fields = ('id', 'image', 'position')
        read_only_fields = ('id', 'position')

    def validate_image(self, value):
        if value.size > MAX_PHOTO_SIZE:
            raise serializers.ValidationError('The photo must not exceed 5 MB.')
        if value.image.format not in ALLOWED_PHOTO_FORMATS:
            raise serializers.ValidationError('Only JPEG, PNG and WEBP photos are allowed.')
        return value


class ItemSerializer(serializers.ModelSerializer):
    owner_id = serializers.IntegerField(read_only=True)
    item_type_title = serializers.CharField(source='item_type.title', read_only=True)
    photos = ItemPhotoSerializer(many=True, read_only=True)

    class Meta:
        model = Item
        fields = (
            'id',
            'owner_id',
            'item_type',
            'item_type_title',
            'title',
            'description',
            'condition',
            'size',
            'exchange_format',
            'status',
            'district',
            'photos',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')

    def validate_status(self, value):
        if self.instance is None:
            if value not in CREATE_STATUSES:
                raise serializers.ValidationError('A new item can only be a draft or active.')
        elif value != self.instance.status and value not in OWNER_TRANSITIONS.get(self.instance.status, ()):
            raise StateConflict(f'Cannot change status from {self.instance.status} to {value}.')
        return value
