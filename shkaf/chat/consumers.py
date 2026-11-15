import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.db.models import Q

from .models import Conversation
from .serializers import MessageSerializer
from .services import group_name, mark_read, send_message

CLOSE_UNAUTHORIZED = 4401
CLOSE_FORBIDDEN = 4403


class ChatConsumer(AsyncJsonWebsocketConsumer):
    """
    Чат диалога в реальном времени.
    Клиент отправляет {"type": "message", "body": "..."} или {"type": "read"}.
    Сервер присылает {"type": "message", "message": {...}}, {"type": "read", ...} или {"type": "error", ...}.
    """

    group = None

    async def connect(self):
        # Сначала принимаем подключение, чтобы клиент получил понятный код закрытия
        await self.accept()
        user = self.scope.get('user')
        if user is None or not user.is_authenticated:
            await self.close(code=CLOSE_UNAUTHORIZED)
            return
        self.conversation = await self.get_conversation(self.scope['url_route']['kwargs']['conversation_id'], user)
        if self.conversation is None:
            await self.close(code=CLOSE_FORBIDDEN)
            return
        self.group = group_name(self.conversation.pk)
        await self.channel_layer.group_add(self.group, self.channel_name)

    async def disconnect(self, code):
        if self.group:
            await self.channel_layer.group_discard(self.group, self.channel_name)

    @classmethod
    async def decode_json(cls, text_data):
        try:
            return json.loads(text_data)
        except ValueError:
            return None

    async def receive_json(self, content, **kwargs):
        if not self.group:
            return
        kind = content.get('type') if isinstance(content, dict) else None
        user = self.scope['user']
        if kind == 'message':
            serializer = MessageSerializer(data={'body': content.get('body')})
            if not serializer.is_valid():
                await self.send_json({'type': 'error', 'errors': serializer.errors})
                return
            await database_sync_to_async(send_message)(self.conversation, user, serializer.validated_data['body'])
        elif kind == 'read':
            await database_sync_to_async(mark_read)(self.conversation, user)
        else:
            await self.send_json({'type': 'error', 'errors': {'type': ['Expected "message" or "read".']}})

    async def chat_message(self, event):
        await self.send_json({'type': 'message', 'message': event['message']})

    async def chat_read(self, event):
        await self.send_json({key: value for key, value in event.items() if key != 'type'} | {'type': 'read'})

    @database_sync_to_async
    def get_conversation(self, conversation_id, user):
        return Conversation.objects.filter(Q(owner=user) | Q(requester=user), pk=conversation_id).first()
