from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from items.models import Item

from .models import MAX_MESSAGE_LENGTH, Conversation, Message


class MessageSerializer(serializers.ModelSerializer):
    conversation_id = serializers.IntegerField(read_only=True)
    sender_id = serializers.IntegerField(read_only=True)
    body = serializers.CharField(max_length=MAX_MESSAGE_LENGTH)

    class Meta:
        model = Message
        fields = ('id', 'conversation_id', 'sender_id', 'body', 'read_at', 'created_at')
        read_only_fields = ('id', 'read_at', 'created_at')


class ParticipantSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ('id', 'username', 'first_name', 'last_name', 'avatar')


class ConversationItemSerializer(serializers.ModelSerializer):
    cover = serializers.SerializerMethodField(help_text='Первое фото объявления')

    class Meta:
        model = Item
        fields = ('id', 'title', 'status', 'cover')

    def get_cover(self, item) -> str | None:
        photo = next(iter(item.photos.all()), None)
        if photo is None:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(photo.image.url) if request else photo.image.url


class ConversationSerializer(serializers.ModelSerializer):
    item = ConversationItemSerializer(read_only=True)
    item_id = serializers.PrimaryKeyRelatedField(
        queryset=Item.objects.filter(deleted_at__isnull=True), source='item', write_only=True
    )
    owner_id = serializers.IntegerField(read_only=True)
    requester_id = serializers.IntegerField(read_only=True)
    companion = serializers.SerializerMethodField(help_text='Второй участник диалога')
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = (
            'id', 'item', 'item_id', 'owner_id', 'requester_id', 'companion', 'last_message',
            'unread_count', 'created_at',
        )
        read_only_fields = ('id', 'created_at')

    def validate_item_id(self, item):
        if item.status != Item.Status.ACTIVE or item.owner.deleted_at is not None:
            raise serializers.ValidationError('This item is not available for messages.')
        if item.owner == self.context['request'].user:
            raise serializers.ValidationError('You cannot start a conversation about your own item.')
        return item

    @extend_schema_field(ParticipantSerializer)
    def get_companion(self, conversation):
        user = self.context['request'].user
        companion = conversation.requester if conversation.owner_id == user.pk else conversation.owner
        return ParticipantSerializer(companion, context=self.context).data

    @extend_schema_field(MessageSerializer(allow_null=True))
    def get_last_message(self, conversation):
        message = getattr(conversation, 'last_message', None)
        return None if message is None else MessageSerializer(message).data

    def get_unread_count(self, conversation) -> int:
        return getattr(conversation, 'unread_count', 0)
