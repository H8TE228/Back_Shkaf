from channels.generic.websocket import AsyncJsonWebsocketConsumer

from chat.consumers import CLOSE_UNAUTHORIZED

from .services import user_group


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    """Новые уведомления пользователя: {"type": "notification", "notification": {...}}."""

    group = None

    async def connect(self):
        await self.accept()
        user = self.scope.get('user')
        if user is None or not user.is_authenticated:
            await self.close(code=CLOSE_UNAUTHORIZED)
            return
        self.group = user_group(user.pk)
        await self.channel_layer.group_add(self.group, self.channel_name)

    async def disconnect(self, code):
        if self.group:
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        """Канал только для отправки с сервера, входящие сообщения игнорируются."""

    async def notification_new(self, event):
        await self.send_json({'type': 'notification', 'notification': event['notification']})
