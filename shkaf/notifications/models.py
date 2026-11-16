from django.conf import settings
from django.contrib.gis.db import models as gis_models
from django.db import models
from django.utils.translation import gettext_lazy as _


class Subscription(models.Model):
    """Подписка на новые объявления (ERD v2). Пустое условие означает «любое»."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subscriptions', verbose_name=_('user')
    )
    item_type = models.ForeignKey(
        'items.ItemType', on_delete=models.CASCADE, null=True, blank=True, related_name='subscriptions',
        verbose_name=_('item type'),
    )
    exchange_format = models.CharField(_('exchange format'), max_length=10, blank=True)
    query = models.CharField(_('query'), max_length=100, blank=True)
    center = gis_models.PointField(_('center'), geography=True, srid=4326, null=True, blank=True)
    radius_km = models.PositiveSmallIntegerField(_('radius, km'), null=True, blank=True)
    is_active = models.BooleanField(_('is active'), default=True)
    created_at = models.DateTimeField(_('creation date'), auto_now_add=True)

    class Meta:
        verbose_name = _('subscription')
        verbose_name_plural = _('subscriptions')
        ordering = ['-created_at', '-pk']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(center__isnull=True, radius_km__isnull=True)
                | models.Q(center__isnull=False, radius_km__isnull=False),
                name='subscription_center_with_radius',
            ),
        ]

    def __str__(self):
        return f'{self.user}: {self.item_type or "любой тип"}'


class Notification(models.Model):
    class Type(models.TextChoices):
        NEW_ITEM = 'new_item', _('new item by subscription')
        EXCHANGE_REQUESTED = 'exchange_requested', _('exchange requested')
        EXCHANGE_AGREED = 'exchange_agreed', _('exchange agreed')
        EXCHANGE_DECLINED = 'exchange_declined', _('exchange declined')
        EXCHANGE_CANCELLED = 'exchange_cancelled', _('exchange cancelled')
        EXCHANGE_COMPLETED = 'exchange_completed', _('exchange completed')

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications', verbose_name=_('user')
    )
    type = models.CharField(_('type'), max_length=30, choices=Type.choices)
    payload = models.JSONField(_('payload'), default=dict, blank=True)
    read_at = models.DateTimeField(_('read date'), null=True, blank=True)
    created_at = models.DateTimeField(_('creation date'), auto_now_add=True)

    class Meta:
        verbose_name = _('notification')
        verbose_name_plural = _('notifications')
        ordering = ['-created_at', '-pk']
        indexes = [models.Index(fields=['user', 'read_at'])]

    def __str__(self):
        return f'{self.user}: {self.type}'
