from django.db import transaction
from django.db.models import Max, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import filters, generics, permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from shkaf.filters import DistanceFilter

from .exceptions import StateConflict
from .models import Item, ItemType
from .permissions import IsOwnerOrReadOnly
from .serializers import ItemPhotoSerializer, ItemSerializer, ItemTypeSerializer

MAX_PHOTOS = 10
PUBLIC_STATUSES = (Item.Status.ACTIVE, Item.Status.RESERVED, Item.Status.GIVEN)
LOCKED_STATUSES = (Item.Status.RESERVED, Item.Status.GIVEN)


def existing_items():
    return (
        Item.objects
        .filter(deleted_at__isnull=True, owner__deleted_at__isnull=True)
        .select_related('item_type')
        .prefetch_related('photos')
    )


def ensure_editable(item):
    if item.status in LOCKED_STATUSES:
        raise StateConflict()


class ItemFilterMixin:
    serializer_class = ItemSerializer
    filter_backends = (DjangoFilterBackend, filters.SearchFilter, DistanceFilter, filters.OrderingFilter)
    distance_field = 'approx_location'
    filterset_fields = ('item_type', 'exchange_format', 'condition', 'status', 'district')
    search_fields = ('title', 'description')
    ordering_fields = ('created_at', 'updated_at')


@extend_schema(tags=['items'])
class ItemTypeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ItemType.objects.all()
    serializer_class = ItemTypeSerializer
    pagination_class = None
    lookup_value_regex = '[0-9]+'


@extend_schema(tags=['items'])
class ItemViewSet(ItemFilterMixin, viewsets.ModelViewSet):
    """Объявления. В списке по умолчанию только активные, другие статусы выбираются через ?status=."""

    permission_classes = (permissions.IsAuthenticatedOrReadOnly, IsOwnerOrReadOnly)
    lookup_value_regex = '[0-9]+'

    def get_queryset(self):
        visible = Q(status__in=PUBLIC_STATUSES)
        if self.request.user.is_authenticated:
            visible |= Q(owner=self.request.user)
        items = existing_items().filter(visible)
        if self.action == 'list' and 'status' not in self.request.query_params:
            items = items.filter(status=Item.Status.ACTIVE)
        return items

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def perform_update(self, serializer):
        ensure_editable(serializer.instance)
        serializer.save()

    def perform_destroy(self, instance):
        ensure_editable(instance)
        instance.deleted_at = timezone.now()
        instance.save()

    @extend_schema(
        request={'multipart/form-data': ItemPhotoSerializer},
        responses={status.HTTP_201_CREATED: ItemPhotoSerializer},
    )
    @action(detail=True, methods=['post'], url_path='photos', parser_classes=[MultiPartParser])
    def add_photo(self, request, pk=None):
        item = self.get_object()
        ensure_editable(item)
        serializer = ItemPhotoSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            # Блокировка не даст двум одновременным загрузкам занять одну позицию
            Item.objects.select_for_update().get(pk=item.pk)
            photos = item.photos.all().order_by()
            if photos.count() >= MAX_PHOTOS:
                raise serializers.ValidationError({'image': f'An item can have at most {MAX_PHOTOS} photos.'})
            last_position = photos.aggregate(last=Max('position'))['last']
            serializer.save(item=item, position=0 if last_position is None else last_position + 1)

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        parameters=[OpenApiParameter('photo_id', int, OpenApiParameter.PATH)],
        request=None,
        responses={status.HTTP_204_NO_CONTENT: None},
    )
    @action(detail=True, methods=['delete'], url_path='photos/(?P<photo_id>[0-9]+)')
    def delete_photo(self, request, pk=None, photo_id=None):
        item = self.get_object()
        ensure_editable(item)
        photo = get_object_or_404(item.photos.all(), pk=photo_id)
        photo.image.delete(save=False)
        photo.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=['me'])
class MyItemsView(ItemFilterMixin, generics.ListAPIView):
    """Все объявления текущего пользователя, включая черновики и архив."""

    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Item.objects.none()
        return existing_items().filter(owner=self.request.user)
