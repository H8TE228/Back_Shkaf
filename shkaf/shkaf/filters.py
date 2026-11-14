from django import forms
from django_filters import rest_framework as django_filters


class IntegerFilter(django_filters.NumberFilter):
    field_class = forms.IntegerField
