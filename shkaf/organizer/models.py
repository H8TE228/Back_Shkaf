from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q

POINT = 'exchange_points.ExchangePoint'
USER = settings.AUTH_USER_MODEL


class PointMember(models.Model):
    class Role(models.TextChoices):
        ORGANIZER = 'organizer', 'Организатор'
        VOLUNTEER = 'volunteer', 'Волонтёр'

    point = models.ForeignKey(POINT, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(USER, on_delete=models.CASCADE, related_name='point_memberships')
    role = models.CharField(max_length=12, choices=Role.choices)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('point', 'user'), name='point_member_unique')]

    def __str__(self):
        return f'{self.point} / {self.user} / {self.role}'


class InventoryRecord(models.Model):
    class Direction(models.TextChoices):
        INTAKE = 'intake', 'Приём'
        ISSUE = 'issue', 'Выдача'

    point = models.ForeignKey(POINT, on_delete=models.PROTECT, related_name='inventory_records')
    item_type = models.ForeignKey('items.ItemType', on_delete=models.PROTECT)
    direction = models.CharField(max_length=6, choices=Direction.choices)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    weight_kg = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                    validators=[MinValueValidator(Decimal('0.01'))])
    client = models.ForeignKey(USER, null=True, blank=True, on_delete=models.SET_NULL,
                               related_name='point_visits')
    recorded_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name='recorded_point_operations')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at', '-pk')
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name='inventory_quantity_positive'),
            models.CheckConstraint(condition=Q(weight_kg__gt=0) | Q(weight_kg__isnull=True),
                                   name='inventory_weight_positive'),
        ]


class VolunteerShift(models.Model):
    point = models.ForeignKey(POINT, on_delete=models.PROTECT, related_name='volunteer_shifts')
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    capacity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name='created_point_shifts')

    class Meta:
        ordering = ('starts_at', 'pk')
        constraints = [
            models.CheckConstraint(condition=Q(ends_at__gt=F('starts_at')), name='shift_end_after_start'),
            models.CheckConstraint(condition=Q(capacity__gt=0), name='shift_capacity_positive'),
        ]


class ShiftAssignment(models.Model):
    class Status(models.TextChoices):
        SIGNED_UP = 'signed_up', 'Записан'
        ATTENDED = 'attended', 'Присутствовал'
        CANCELLED = 'cancelled', 'Отменено'

    shift = models.ForeignKey(VolunteerShift, on_delete=models.CASCADE, related_name='assignments')
    user = models.ForeignKey(USER, on_delete=models.CASCADE)
    status = models.CharField(max_length=9, choices=Status.choices, default=Status.SIGNED_UP)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('shift', 'user'), name='shift_user_unique')]


class PointAuditLog(models.Model):
    point = models.ForeignKey(POINT, on_delete=models.PROTECT, related_name='organizer_audit')
    actor = models.ForeignKey(USER, on_delete=models.PROTECT)
    action = models.CharField(max_length=40)
    data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at', '-pk')
