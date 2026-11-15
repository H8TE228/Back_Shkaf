from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Bookmark(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bookmarks', verbose_name=_('user')
    )
    item = models.ForeignKey(
        'items.Item', on_delete=models.CASCADE, related_name='bookmarks',
        null=True, blank=True, verbose_name=_('item'),
    )
    point = models.ForeignKey(
        'exchange_points.ExchangePoint', on_delete=models.CASCADE, related_name='bookmarks',
        null=True, blank=True, verbose_name=_('exchange point'),
    )
    created_at = models.DateTimeField(_('creation date'), auto_now_add=True)

    class Meta:
        verbose_name = _('bookmark')
        verbose_name_plural = _('bookmarks')
        ordering = ('-created_at', '-pk')
        constraints = (
            models.CheckConstraint(
                condition=(
                    models.Q(item__isnull=False, point__isnull=True)
                    | models.Q(item__isnull=True, point__isnull=False)
                ),
                name='bookmark_exactly_one_target',
            ),
            models.UniqueConstraint(fields=['user', 'item'], name='bookmark_user_item_unique'),
            models.UniqueConstraint(fields=['user', 'point'], name='bookmark_user_point_unique'),
        )

    def __str__(self):
        return f'{self.user_id}: {self.item or self.point}'
