from django.db import IntegrityError, transaction
from django.db.models import Count, Max, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import mixins, permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Conversation, Message
from .serializers import ConversationSerializer, MessageSerializer
from .services import mark_read, send_message


def conversations_for(user):
    last_message = Message.objects.filter(conversation=OuterRef('pk')).order_by('-created_at', '-pk')
    return (
        Conversation.objects
        .filter(Q(owner=user) | Q(requester=user))
        .select_related('item', 'owner', 'requester')
        .prefetch_related('item__photos')
        .annotate(
            unread_count=Count(
                'messages', filter=Q(messages__read_at__isnull=True) & ~Q(messages__sender=user)
            ),
            last_message_id=Subquery(last_message.values('pk')[:1]),
            last_activity=Coalesce(Max('messages__created_at'), 'created_at'),
        )
        .order_by('-last_activity', '-pk')
    )


def attach_last_messages(conversations):
    messages = Message.objects.in_bulk([c.last_message_id for c in conversations if c.last_message_id])
    for conversation in conversations:
        conversation.last_message = messages.get(conversation.last_message_id)
    return conversations


@extend_schema(tags=['conversations'])
class ConversationViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                          viewsets.GenericViewSet):
    """Диалоги по вещам. Пользователь видит только диалоги, в которых участвует."""

    serializer_class = ConversationSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_value_regex = '[0-9]+'

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Conversation.objects.none()
        return conversations_for(self.request.user)

    def list(self, request, *args, **kwargs):
        conversations = attach_last_messages(list(self.get_queryset()))
        return Response(self.get_serializer(conversations, many=True).data)

    def retrieve(self, request, *args, **kwargs):
        conversation = attach_last_messages([self.get_object()])[0]
        return Response(self.get_serializer(conversation).data)

    @extend_schema(responses={200: ConversationSerializer, 201: ConversationSerializer})
    def create(self, request, *args, **kwargs):
        """Начинает диалог по вещи или возвращает уже существующий (200)."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = serializer.validated_data['item']
        try:
            with transaction.atomic():
                conversation, created = Conversation.objects.get_or_create(
                    item=item, requester=request.user, defaults={'owner': item.owner}
                )
        except IntegrityError:
            conversation, created = Conversation.objects.get(item=item, requester=request.user), False

        conversation = attach_last_messages([self.get_queryset().get(pk=conversation.pk)])[0]
        return Response(
            self.get_serializer(conversation).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @extend_schema(methods=['GET'], responses=MessageSerializer(many=True))
    @extend_schema(methods=['POST'], request=MessageSerializer, responses={201: MessageSerializer})
    @action(detail=True, methods=['get', 'post'])
    def messages(self, request, pk=None):
        """GET: сообщения по порядку. POST: отправка сообщения, оно же придёт участникам по WebSocket."""
        conversation = self.get_object()
        if request.method == 'GET':
            messages = conversation.messages.order_by('created_at', 'pk')
            return Response(MessageSerializer(messages, many=True).data)

        serializer = MessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = send_message(conversation, request.user, serializer.validated_data['body'])
        return Response(MessageSerializer(message).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses=inline_serializer('MarkRead', {'marked_read': serializers.IntegerField()}))
    @action(detail=True, methods=['post'])
    def read(self, request, pk=None):
        """Отмечает прочитанными сообщения собеседника."""
        return Response({'marked_read': mark_read(self.get_object(), request.user)})
