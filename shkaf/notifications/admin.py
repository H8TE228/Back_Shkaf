from django.contrib import admin

from .models import Notification, Subscription


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ['user', 'item_type', 'exchange_format', 'query', 'radius_km', 'is_active', 'created_at']
    list_filter = ['is_active', 'item_type']
    search_fields = ['user__email', 'query']


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'type', 'read_at', 'created_at']
    list_filter = ['type']
    search_fields = ['user__email']
