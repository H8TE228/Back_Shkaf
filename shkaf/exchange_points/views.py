from django_filters import rest_framework as django_filters
from drf_spectacular.utils import extend_schema
from rest_framework import filters, permissions, viewsets
from rest_framework.parsers import JSONParser

from .filters import ExchangePointFilter
from .models import ExchangePoint
from .serializers import ExchangePointSerializer


@extend_schema(tags=['exchange-points'])
class ExchangePointViewSet(viewsets.ModelViewSet):
    queryset = (
        ExchangePoint.objects.select_related('address').prefetch_related('item_types')
        .order_by('-created_at', '-id')
    )
    serializer_class = ExchangePointSerializer
    parser_classes = (JSONParser,)
    http_method_names = ('get', 'post', 'patch', 'head', 'options')
    filter_backends = (django_filters.DjangoFilterBackend, filters.SearchFilter)
    filterset_class = ExchangePointFilter
    search_fields = ('title',)
    pagination_class = None
    lookup_value_regex = '[0-9]+'

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.AllowAny()]
        return [permissions.IsAdminUser()]
