from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin

from .models import Address, ExchangePoint


@admin.register(Address)
class AddressAdmin(GISModelAdmin):
    list_display = ['city', 'district', 'street', 'building']
    list_filter = ['city']
    search_fields = ['city', 'district', 'street']


@admin.register(ExchangePoint)
class ExchangePointAdmin(admin.ModelAdmin):
    list_display = ['title', 'address', 'status', 'phone', 'updated_at']
    list_filter = ['status', 'address__city', 'item_types']
    search_fields = ['title', 'address__street', 'address__city']
    autocomplete_fields = ['address', 'verified_by']
    filter_horizontal = ['item_types']
    readonly_fields = ['created_at', 'updated_at']
