from django_filters import rest_framework as django_filters

from shkaf.filters import IntegerFilter

from .models import ExchangePoint


class ExchangePointFilter(django_filters.FilterSet):
    city = django_filters.CharFilter(field_name='address__city')
    district = django_filters.CharFilter(field_name='address__district')
    exchange_format = django_filters.ChoiceFilter(choices=ExchangePoint.Format.choices, method='filter_format')
    item_type_id = IntegerFilter(field_name='item_types__id', distinct=True)
    item_type = django_filters.CharFilter(field_name='item_types__title', lookup_expr='iexact', distinct=True)

    class Meta:
        model = ExchangePoint
        fields = ('city', 'district', 'status', 'exchange_format', 'item_type_id', 'item_type')

    def filter_format(self, queryset, name, value):
        return queryset.filter(formats__contains=[value])
