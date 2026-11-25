from django.urls import path

from . import views

base = 'organizer/points/<int:point_id>'
shifts = f'{base}/shifts'

urlpatterns = [
    path('me/point-roles', views.MyPointRolesView.as_view(), name='point-roles'),
    path(f'{base}/status', views.PointStatusView.as_view(), name='organizer-point-status'),
    path(f'{base}/inventory', views.InventoryView.as_view(), name='organizer-inventory'),
    path(shifts, views.ShiftListView.as_view(), name='organizer-shifts'),
    path(f'{shifts}/<int:shift_id>', views.ShiftDetailView.as_view(), name='organizer-shift'),
    path(f'{shifts}/<int:shift_id>/signup', views.ShiftSignupView.as_view(), name='organizer-signup'),
    path(f'{shifts}/<int:shift_id>/assignments', views.ShiftAssignmentsView.as_view(), name='organizer-assignments'),
    path(f'{shifts}/<int:shift_id>/assignments/<int:assignment_id>/attend',
         views.ShiftAttendanceView.as_view(), name='organizer-attend'),
]
