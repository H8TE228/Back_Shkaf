from django_filters import rest_framework as django_filters
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field

from shkaf.filters import IntegerFilter

from .models import Item


class ItemFilter(django_filters.FilterSet):
    owner_id = IntegerFilter(field_name='owner_id', method='filter_owner_id', help_text='ID владельца объявления')
    item_type_id = IntegerFilter(field_name='item_type_id', method='filter_item_type_id')
    item_type = django_filters.CharFilter(field_name='item_type__title', lookup_expr='iexact')

    @extend_schema_field(OpenApiTypes.INT)
    def filter_owner_id(self, queryset, name, value):
        return queryset.filter(**{name: value})

    @extend_schema_field(OpenApiTypes.INT)
    def filter_item_type_id(self, queryset, name, value):
        return queryset.filter(**{name: value})

    class Meta:
        model = Item
        fields = ('owner_id', 'item_type_id', 'item_type', 'exchange_format', 'condition', 'status', 'district')
