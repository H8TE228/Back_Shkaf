from django_filters import rest_framework as django_filters
from drf_spectacular.utils import extend_schema
from rest_framework import filters, permissions, viewsets
from rest_framework.parsers import JSONParser

from .models import ExchangePoint
from .serializers import ExchangePointSerializer


class ExchangePointFilter(django_filters.FilterSet):
    city = django_filters.CharFilter(field_name='address__city')
    district = django_filters.CharFilter(field_name='address__district')
    exchange_format = django_filters.ChoiceFilter(choices=ExchangePoint.Format.choices, method='filter_format')

    class Meta:
        model = ExchangePoint
        fields = ('city', 'district', 'status', 'exchange_format')

    def filter_format(self, queryset, name, value):
        return queryset.filter(formats__contains=[value])


@extend_schema(tags=['exchange-points'])
class ExchangePointViewSet(viewsets.ModelViewSet):
    queryset = ExchangePoint.objects.select_related('address').order_by('-created_at', '-id')
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
