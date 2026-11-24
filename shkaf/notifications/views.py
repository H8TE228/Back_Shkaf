from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import mixins, permissions, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from shkaf.pagination import StandardPagination

from .models import Notification, Subscription
from .serializers import NotificationSerializer, SubscriptionSerializer


@extend_schema(tags=['me'])
class SubscriptionViewSet(viewsets.ModelViewSet):
    """Мои подписки на новые объявления. Пустое условие означает «любое»."""

    serializer_class = SubscriptionSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_value_regex = '[0-9]+'
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Subscription.objects.none()
        return self.request.user.subscriptions.all()

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


@extend_schema(tags=['me'])
class NotificationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Мои уведомления, сначала новые. ?unread=true — только непрочитанные."""

    serializer_class = NotificationSerializer
    pagination_class = StandardPagination
    permission_classes = (permissions.IsAuthenticated,)
    lookup_value_regex = '[0-9]+'

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Notification.objects.none()
        notifications = self.request.user.notifications.all()
        if self.request.query_params.get('unread') in ('true', '1'):
            notifications = notifications.filter(read_at__isnull=True)
        return notifications

    @extend_schema(request=None, responses=NotificationSerializer)
    @action(detail=True, methods=['post'])
    def read(self, request, pk=None):
        notification = self.get_object()
        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.save(update_fields=['read_at'])
        return Response(self.get_serializer(notification).data)

    @extend_schema(request=None, responses=inline_serializer('MarkAllRead', {'marked_read': serializers.IntegerField()}))
    @action(detail=False, methods=['post'], url_path='read-all')
    def read_all(self, request):
        updated = request.user.notifications.filter(read_at__isnull=True).update(read_at=timezone.now())
        return Response({'marked_read': updated})

    @extend_schema(responses=inline_serializer('UnreadCount', {'count': serializers.IntegerField()}))
    @action(detail=False, methods=['get'], url_path='unread-count')
    def unread_count(self, request):
        return Response({'count': request.user.notifications.filter(read_at__isnull=True).count()})
