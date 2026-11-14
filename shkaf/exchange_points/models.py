from django.conf import settings
from django.contrib.gis.db import models as gis_models
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils.translation import gettext_lazy as _


class Address(models.Model):
    """Адрес пункта обмена. У пользователей адреса нет, только город и район (ERD v2)."""

    country = models.CharField(_('country'), max_length=100, default='Россия')
    region = models.CharField(_('region'), max_length=100, blank=True)
    city = models.CharField(_('city'), max_length=100)
    district = models.CharField(_('district'), max_length=100, blank=True)
    street = models.CharField(_('street'), max_length=150)
    building = models.CharField(_('building'), max_length=20)
    postal_code = models.CharField(_('postal code'), max_length=10, blank=True)
    location = gis_models.PointField(_('location'), geography=True, srid=4326)

    class Meta:
        verbose_name = _('address')
        verbose_name_plural = _('addresses')

    def __str__(self):
        return f'{self.city}, {self.street}, {self.building}'


class ExchangePoint(models.Model):
    class Format(models.TextChoices):
        FREE = 'free', _('free')
        POINTS = 'points', _('points')
        CHARITY = 'charity', _('charity')

    class Status(models.TextChoices):
        ACTIVE = 'active', _('active')
        NEEDS_CHECK = 'needs_check', _('needs check')
        CLOSED = 'closed', _('closed')

    address = models.OneToOneField(
        Address, on_delete=models.PROTECT, related_name='exchange_point', verbose_name=_('address')
    )
    title = models.CharField(_('title'), max_length=200)
    description = models.TextField(_('description'), blank=True)
    opening_hours = models.JSONField(_('opening hours'), default=dict, blank=True)
    phone = models.CharField(_('phone'), max_length=20, blank=True)
    email = models.EmailField(_('email'), blank=True)
    website = models.URLField(_('website'), max_length=255, blank=True)
    formats = ArrayField(
        models.CharField(max_length=10, choices=Format.choices),
        verbose_name=_('formats'), default=list, blank=True,
    )
    status = models.CharField(
        _('status'), max_length=11, choices=Status.choices, default=Status.NEEDS_CHECK
    )
    verified_at = models.DateTimeField(_('verification date'), null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='verified_exchange_points', verbose_name=_('verified by'),
    )
    item_types = models.ManyToManyField(
        'items.ItemType', related_name='exchange_points', blank=True, verbose_name=_('item types')
    )
    picture = models.ImageField(_('picture'), upload_to='exchange_points/', blank=True)
    created_at = models.DateTimeField(_('creation date'), auto_now_add=True)
    updated_at = models.DateTimeField(_('last update date'), auto_now=True)

    class Meta:
        verbose_name = _('exchange point')
        verbose_name_plural = _('exchange points')

    def __str__(self):
        return self.title
