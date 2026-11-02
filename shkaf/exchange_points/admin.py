from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin

from .models import Address


@admin.register(Address)
class AddressAdmin(GISModelAdmin):
    list_display = ['city', 'district', 'street', 'building']
    list_filter = ['city']
    search_fields = ['city', 'district', 'street']
