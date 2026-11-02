from django.contrib.auth.models import AbstractUser
from django.contrib.gis.db import models as gis_models
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from shkaf.geo import round_point


class User(AbstractUser):
    class Role(models.TextChoices):
        USER = 'user', _('user')
        MODERATOR = 'moderator', _('moderator')
        ADMIN = 'admin', _('admin')

    # username, first_name, last_name
    email = models.EmailField(_('email address'), unique=True)
    phone_number = models.CharField(
        _('phone number'),
        max_length=20,
        blank=True,
        validators=[
            RegexValidator(
                regex=r'^\+?1?\d{9,15}$',
                message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed."
            )
        ]
    )
    role = models.CharField(_('role'), max_length=20, choices=Role.choices, default=Role.USER)
    city = models.CharField(_('city'), max_length=100, blank=True)
    district = models.CharField(_('district'), max_length=100, blank=True)
    approx_location = gis_models.PointField(
        _('approximate location'), geography=True, srid=4326, null=True, blank=True
    )
    avatar = models.ImageField(_('avatar'), upload_to='avatars/', blank=True)
    points_balance = models.IntegerField(_('points balance'), default=0)
    email_verified_at = models.DateTimeField(_('email verification date'), null=True, blank=True)
    phone_verified_at = models.DateTimeField(_('phone verification date'), null=True, blank=True)
    created_at = models.DateTimeField(_('creation date'), auto_now_add=True)
    updated_at = models.DateTimeField(_('last update date'), auto_now=True)
    deleted_at = models.DateTimeField(_('deletion date'), null=True, blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')
        constraints = [
            models.UniqueConstraint(
                fields=['phone_number'],
                name='phone_number_non_empty',
                condition=~models.Q(phone_number="")
            ),
            models.CheckConstraint(
                condition=models.Q(points_balance__gte=0),
                name='points_balance_non_negative',
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.username:
            self.username = self.email
        self.approx_location = round_point(self.approx_location)
        super().save(*args, **kwargs)

    def anonymize(self):
        """Удаляет персональные данные: история передач и отзывы других людей сохраняются."""
        if self.avatar:
            self.avatar.delete(save=False)
        self.email = f'deleted-{self.pk}@deleted.invalid'
        self.username = f'deleted-{self.pk}'
        self.first_name = ''
        self.last_name = ''
        self.phone_number = ''
        self.city = ''
        self.district = ''
        self.approx_location = None
        self.email_verified_at = None
        self.phone_verified_at = None
        self.is_active = False
        self.deleted_at = timezone.now()
        self.set_unusable_password()
        self.save()

    def __str__(self):
        return self.email
