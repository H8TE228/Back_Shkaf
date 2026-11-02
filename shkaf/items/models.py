from django.conf import settings
from django.contrib.gis.db import models as gis_models
from django.db import models
from django.utils.translation import gettext_lazy as _

from shkaf.geo import round_point


class ItemType(models.Model):
    title = models.CharField(_('title'), max_length=100, unique=True)
    description = models.TextField(_('description'), blank=True)
    avg_weight_kg = models.DecimalField(
        _('average weight, kg'), max_digits=6, decimal_places=2, null=True, blank=True
    )
    co2_per_kg = models.DecimalField(
        _('CO2 per kg'), max_digits=6, decimal_places=2, null=True, blank=True
    )

    class Meta:
        verbose_name = _('item type')
        verbose_name_plural = _('item types')
        ordering = ['title']

    def __str__(self):
        return self.title


class Item(models.Model):
    class Condition(models.TextChoices):
        NEW = 'new', _('new')
        GOOD = 'good', _('good')
        USED = 'used', _('used')

    class ExchangeFormat(models.TextChoices):
        FREE = 'free', _('free')
        SWAP = 'swap', _('swap')
        POINTS = 'points', _('points')

    class Status(models.TextChoices):
        DRAFT = 'draft', _('draft')
        ACTIVE = 'active', _('active')
        RESERVED = 'reserved', _('reserved')
        GIVEN = 'given', _('given')
        ARCHIVED = 'archived', _('archived')

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='items', verbose_name=_('owner')
    )
    item_type = models.ForeignKey(
        ItemType, on_delete=models.PROTECT, related_name='items', verbose_name=_('item type')
    )
    title = models.CharField(_('title'), max_length=150)
    description = models.TextField(_('description'), blank=True)
    condition = models.CharField(_('condition'), max_length=10, choices=Condition.choices)
    size = models.CharField(_('size'), max_length=30, blank=True)
    exchange_format = models.CharField(_('exchange format'), max_length=10, choices=ExchangeFormat.choices)
    status = models.CharField(_('status'), max_length=10, choices=Status.choices, default=Status.DRAFT)
    district = models.CharField(_('district'), max_length=100, blank=True)
    approx_location = gis_models.PointField(
        _('approximate location'), geography=True, srid=4326, null=True, blank=True
    )
    created_at = models.DateTimeField(_('creation date'), auto_now_add=True)
    updated_at = models.DateTimeField(_('last update date'), auto_now=True)
    deleted_at = models.DateTimeField(_('deletion date'), null=True, blank=True)

    class Meta:
        verbose_name = _('item')
        verbose_name_plural = _('items')
        ordering = ['-created_at']
        indexes = [models.Index(fields=['status', 'item_type'])]

    def save(self, *args, **kwargs):
        self.approx_location = round_point(self.approx_location)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class ItemPhoto(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='photos', verbose_name=_('item'))
    image = models.ImageField(_('image'), upload_to='items/')
    position = models.PositiveSmallIntegerField(_('position'), default=0)

    class Meta:
        verbose_name = _('item photo')
        verbose_name_plural = _('item photos')
        ordering = ['position']
        constraints = [
            models.UniqueConstraint(fields=['item', 'position'], name='item_photo_position_unique')
        ]

    def __str__(self):
        return f'{self.item} #{self.position}'
