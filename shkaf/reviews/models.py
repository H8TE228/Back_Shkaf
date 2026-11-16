from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

MAX_COMMENT_LENGTH = 2000


class Review(models.Model):
    """Отзыв участника завершённой передачи о втором участнике (ERD v2)."""

    exchange = models.ForeignKey(
        'exchanges.Exchange', on_delete=models.PROTECT, related_name='reviews', verbose_name=_('exchange')
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='written_reviews', verbose_name=_('author')
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='received_reviews',
        verbose_name=_('target user'),
    )
    rating = models.PositiveSmallIntegerField(_('rating'))
    comment = models.TextField(_('comment'), blank=True, max_length=MAX_COMMENT_LENGTH)
    created_at = models.DateTimeField(_('creation date'), auto_now_add=True)
    updated_at = models.DateTimeField(_('last update date'), auto_now=True)

    class Meta:
        verbose_name = _('review')
        verbose_name_plural = _('reviews')
        ordering = ['-created_at', '-pk']
        indexes = [models.Index(fields=['target_user', 'created_at'])]
        constraints = [
            models.UniqueConstraint(fields=['exchange', 'author'], name='review_one_per_exchange_author'),
            models.CheckConstraint(condition=models.Q(rating__gte=1, rating__lte=5), name='review_rating_1_5'),
            models.CheckConstraint(
                condition=~models.Q(author=models.F('target_user')), name='review_not_about_self'
            ),
        ]

    def __str__(self):
        return f'{self.author} → {self.target_user}: {self.rating}'
