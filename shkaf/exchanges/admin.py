from django.contrib import admin

from .models import Exchange


@admin.register(Exchange)
class ExchangeAdmin(admin.ModelAdmin):
    list_display = ['item', 'giver', 'receiver', 'status', 'created_at', 'completed_at']
    list_filter = ['status']
    search_fields = ['item__title', 'giver__email', 'receiver__email']
    readonly_fields = [
        'item', 'giver', 'receiver', 'status', 'giver_confirmed_at', 'receiver_confirmed_at',
        'completed_at', 'created_at', 'updated_at',
    ]

    def has_add_permission(self, request):
        return False
