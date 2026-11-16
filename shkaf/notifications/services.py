from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

from .models import Notification
from .serializers import NotificationSerializer


def user_group(user_id):
    return f'user_{user_id}'


def notify(user_id, notification_type, payload):
    """Создаёт уведомление и после записи в базу отправляет его в открытые WebSocket пользователя."""
    notification = Notification.objects.create(user_id=user_id, type=notification_type, payload=payload)
    data = dict(NotificationSerializer(notification).data)
    layer = get_channel_layer()
    if layer is not None:
        transaction.on_commit(lambda: async_to_sync(layer.group_send)(
            user_group(user_id), {'type': 'notification.new', 'notification': data}
        ))
    return notification


def exchange_payload(exchange):
    return {'exchange_id': exchange.pk, 'item_id': exchange.item_id, 'item_title': exchange.item.title}
