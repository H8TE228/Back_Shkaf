from django_filters import rest_framework as django_filters

from .models import Bookmark


class BookmarkFilter(django_filters.FilterSet):
    type = django_filters.ChoiceFilter(choices=(('item', 'item'), ('point', 'point')), method='filter_type')

    class Meta:
        model = Bookmark
        fields = ('type',)

    def filter_type(self, queryset, name, value):
        return queryset.filter(**{f'{value}__isnull': False})
