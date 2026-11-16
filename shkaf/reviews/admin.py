from django.contrib import admin

from .models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['author', 'target_user', 'rating', 'created_at']
    list_filter = ['rating']
    search_fields = ['author__email', 'target_user__email', 'comment']
    readonly_fields = ['exchange', 'author', 'target_user', 'created_at', 'updated_at']
