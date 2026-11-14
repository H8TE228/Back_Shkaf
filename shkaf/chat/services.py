from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.utils import timezone

from .models import Message
from .serializers import MessageSerializer


def group_name(conversation_id):
    return f'conversation_{conversation_id}'


def broadcast(conversation_id, event):
    """Отправляет событие подключённым участникам диалога после успешной записи в базу."""
    layer = get_channel_layer()
    if layer is not None:
        transaction.on_commit(lambda: async_to_sync(layer.group_send)(group_name(conversation_id), event))


def send_message(conversation, sender, body):
    message = Message.objects.create(conversation=conversation, sender=sender, body=body)
    broadcast(conversation.pk, {'type': 'chat.message', 'message': dict(MessageSerializer(message).data)})
    return message


def mark_read(conversation, reader):
    """Отмечает прочитанными все сообщения собеседника."""
    read_at = timezone.now()
    updated = conversation.messages.filter(read_at__isnull=True).exclude(sender=reader).update(read_at=read_at)
    if updated:
        broadcast(conversation.pk, {
            'type': 'chat.read',
            'conversation_id': conversation.pk,
            'reader_id': reader.pk,
            'read_at': read_at.isoformat(),
        })
    return updated
