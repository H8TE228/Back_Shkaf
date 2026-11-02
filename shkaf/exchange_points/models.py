from django.contrib.gis.db import models as gis_models
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
