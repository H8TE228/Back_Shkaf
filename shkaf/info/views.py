from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, serializers, viewsets

from .models import Article, ArticleMedia


class ArticleMediaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArticleMedia
        fields = ('id', 'media_type', 'url', 'description', 'position')


class ArticleSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Article
        fields = ('id', 'slug', 'title', 'published_at')


class ArticleSerializer(ArticleSummarySerializer):
    media = ArticleMediaSerializer(many=True, read_only=True)

    class Meta(ArticleSummarySerializer.Meta):
        fields = (*ArticleSummarySerializer.Meta.fields, 'body', 'media', 'updated_at')


@extend_schema(tags=['info'])
class ArticleViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Article.objects.all()
    serializer_class = ArticleSerializer
    permission_classes = (permissions.AllowAny,)
    lookup_field = 'slug'

    def get_queryset(self):
        articles = self.queryset.filter(published_at__lte=timezone.now())
        if self.action == 'retrieve':
            return articles.prefetch_related('media')
        return articles

    def get_serializer_class(self):
        return ArticleSummarySerializer if self.action == 'list' else ArticleSerializer
