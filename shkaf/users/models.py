from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
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
    created_at = models.DateTimeField(_('creation date'), auto_now_add=True)
    updated_at = models.DateTimeField(_('last update date'), auto_now=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')
 
    def save(self, *args, **kwargs):
        if not self.username:
            self.username = self.email
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['phone_number'],
                name='phone_number_non_empty',
                condition=~models.Q(phone_number="")
            )
        ]
