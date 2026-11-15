from django.db.models import Q
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, status
from rest_framework.response import Response

from exchange_points.models import ExchangePoint
from items.querysets import visible_items

from .filters import BookmarkFilter
from .models import Bookmark
from .serializers import BookmarkSerializer


@extend_schema(tags=['bookmarks'])
class MyBookmarksView(generics.ListAPIView):
    serializer_class = BookmarkSerializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = (DjangoFilterBackend,)
    filterset_class = BookmarkFilter
    pagination_class = None

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Bookmark.objects.none()
        return (
            Bookmark.objects.filter(user=self.request.user)
            .filter(Q(point__isnull=False) | Q(item__in=visible_items(self.request.user)))
            .select_related('item__item_type', 'point__address')
            .prefetch_related('item__photos', 'point__item_types')
        )


class TargetBookmarkView(generics.GenericAPIView):
    serializer_class = BookmarkSerializer
    permission_classes = (permissions.IsAuthenticated,)
    http_method_names = ('post', 'delete', 'options')
    target_field = None

    @extend_schema(tags=['bookmarks'], request=None, responses={200: BookmarkSerializer, 201: BookmarkSerializer})
    def post(self, request, pk):
        target = get_object_or_404(self.get_queryset(), pk=pk)
        bookmark, created = Bookmark.objects.get_or_create(user=request.user, **{self.target_field: target})
        return Response(
            self.get_serializer(bookmark).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @extend_schema(tags=['bookmarks'], request=None, responses={204: None})
    def delete(self, request, pk):
        # Удаление закладки разрешено, даже если её цель больше не видна пользователю.
        Bookmark.objects.filter(user=request.user, **{f'{self.target_field}_id': pk}).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ItemBookmarkView(TargetBookmarkView):
    target_field = 'item'

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return visible_items(self.request.user).none()
        return visible_items(self.request.user)


class PointBookmarkView(TargetBookmarkView):
    target_field = 'point'
    queryset = ExchangePoint.objects.select_related('address').prefetch_related('item_types')
