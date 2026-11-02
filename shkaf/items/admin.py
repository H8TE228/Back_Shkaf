from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin

from .models import Item, ItemPhoto, ItemType


@admin.register(ItemType)
class ItemTypeAdmin(admin.ModelAdmin):
    list_display = ['title', 'avg_weight_kg', 'co2_per_kg']
    search_fields = ['title']


class ItemPhotoInline(admin.TabularInline):
    model = ItemPhoto
    extra = 1


@admin.register(Item)
class ItemAdmin(GISModelAdmin):
    list_display = ['title', 'owner', 'item_type', 'exchange_format', 'status', 'created_at']
    list_filter = ['status', 'exchange_format', 'condition', 'item_type']
    search_fields = ['title', 'description', 'owner__email']
    autocomplete_fields = ['owner', 'item_type']
    readonly_fields = ['created_at', 'updated_at', 'deleted_at']
    inlines = [ItemPhotoInline]
