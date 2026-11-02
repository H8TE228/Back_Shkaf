from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


class CustomUserAdmin(UserAdmin):
    model = User
    list_display = ['email', 'username', 'role', 'city', 'points_balance', 'is_active', 'created_at']
    list_filter = ['role', 'is_active', 'is_staff']
    search_fields = ['email', 'username', 'first_name', 'last_name', 'phone_number']
    ordering = ['-created_at']
    readonly_fields = ['created_at', 'updated_at', 'deleted_at']
    fieldsets = UserAdmin.fieldsets + (
        ('Профиль', {'fields': (
            'phone_number', 'role', 'city', 'district', 'avatar', 'points_balance',
            'email_verified_at', 'phone_verified_at', 'created_at', 'updated_at', 'deleted_at',
        )}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'username', 'usable_password', 'password1', 'password2'),
        }),
    )


admin.site.register(User, CustomUserAdmin)
