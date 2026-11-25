from django.contrib import admin

from .models import InventoryRecord, PointAuditLog, PointMember, VolunteerShift

admin.site.register(PointMember)


@admin.register(InventoryRecord, VolunteerShift, PointAuditLog)
class OrganizerHistoryAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
