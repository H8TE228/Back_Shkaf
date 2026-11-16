from django.contrib.auth import get_user_model
from django.db.models import Avg, Count
from django.shortcuts import get_object_or_404
from django_filters import rest_framework as django_filters
from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, viewsets
from rest_framework.response import Response

from .models import Review
from .permissions import IsAuthorOrReadOnly
from .serializers import RatingSerializer, ReviewSerializer


class ReviewFilter(django_filters.FilterSet):
    target_user = django_filters.NumberFilter(field_name='target_user_id', help_text='Отзывы о пользователе')
    author = django_filters.NumberFilter(field_name='author_id', help_text='Отзывы, написанные пользователем')

    class Meta:
        model = Review
        fields = ('target_user', 'author', 'rating')


@extend_schema(tags=['reviews'])
class ReviewViewSet(viewsets.ModelViewSet):
    """Отзывы видны всем. Оставить отзыв может участник завершённой передачи, менять и удалять — только автор."""

    serializer_class = ReviewSerializer
    permission_classes = (permissions.IsAuthenticatedOrReadOnly, IsAuthorOrReadOnly)
    filter_backends = (django_filters.DjangoFilterBackend,)
    filterset_class = ReviewFilter
    lookup_value_regex = '[0-9]+'
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']
    queryset = (
        Review.objects.select_related('exchange__item', 'author')
        .prefetch_related('exchange__item__photos')
    )


@extend_schema(tags=['reviews'], responses=RatingSerializer)
class UserRatingView(generics.GenericAPIView):
    """Средняя оценка пользователя и количество отзывов о нём."""

    serializer_class = RatingSerializer
    queryset = get_user_model().objects.filter(deleted_at__isnull=True)

    def get(self, request, pk):
        user = get_object_or_404(self.get_queryset(), pk=pk)
        summary = Review.objects.filter(target_user=user).aggregate(average=Avg('rating'), count=Count('pk'))
        average = summary['average']
        return Response(RatingSerializer({
            'user_id': user.pk,
            'average': None if average is None else round(average, 1),
            'count': summary['count'],
        }).data)
