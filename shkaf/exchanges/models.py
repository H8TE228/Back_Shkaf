from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_fsm import FSMField, transition

ACTIVE_STATUSES = ('agreed', 'completed')
OPEN_STATUSES = ('requested', 'agreed')


class Exchange(models.Model):
    """
    Передача вещи (ERD v2, бывшая Transaction).
    requested → agreed → completed; requested → declined; requested или agreed → cancelled.
    """

    class Status(models.TextChoices):
        REQUESTED = 'requested', _('requested')
        AGREED = 'agreed', _('agreed')
        COMPLETED = 'completed', _('completed')
        DECLINED = 'declined', _('declined')
        CANCELLED = 'cancelled', _('cancelled')

    item = models.ForeignKey(
        'items.Item', on_delete=models.PROTECT, related_name='exchanges', verbose_name=_('item')
    )
    giver = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='given_exchanges', verbose_name=_('giver')
    )
    receiver = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='received_exchanges',
        verbose_name=_('receiver'),
    )
    status = FSMField(_('status'), max_length=10, choices=Status.choices, default=Status.REQUESTED)
    giver_confirmed_at = models.DateTimeField(_('giver confirmation date'), null=True, blank=True)
    receiver_confirmed_at = models.DateTimeField(_('receiver confirmation date'), null=True, blank=True)
    completed_at = models.DateTimeField(_('completion date'), null=True, blank=True)
    created_at = models.DateTimeField(_('creation date'), auto_now_add=True)
    updated_at = models.DateTimeField(_('last update date'), auto_now=True)

    class Meta:
        verbose_name = _('exchange')
        verbose_name_plural = _('exchanges')
        ordering = ['-created_at', '-pk']
        indexes = [models.Index(fields=['receiver']), models.Index(fields=['giver'])]
        constraints = [
            # Защита от двойного резерва: у вещи не больше одной согласованной или завершённой передачи
            models.UniqueConstraint(
                fields=['item'], condition=models.Q(status__in=ACTIVE_STATUSES), name='exchange_one_active_per_item'
            ),
            models.UniqueConstraint(
                fields=['item', 'receiver'], condition=models.Q(status__in=OPEN_STATUSES),
                name='exchange_one_open_request_per_receiver',
            ),
            models.CheckConstraint(
                condition=~models.Q(giver=models.F('receiver')), name='exchange_participants_differ'
            ),
        ]

    def __str__(self):
        return f'{self.item} → {self.receiver}'

    def participant_role(self, user):
        if user.pk == self.giver_id:
            return 'giver'
        if user.pk == self.receiver_id:
            return 'receiver'
        return None

    @transition(field=status, source=Status.REQUESTED, target=Status.AGREED)
    def agree(self):
        pass

    @transition(field=status, source=Status.REQUESTED, target=Status.DECLINED)
    def decline(self):
        pass

    @transition(field=status, source=[Status.REQUESTED, Status.AGREED], target=Status.CANCELLED)
    def cancel(self):
        pass

    @transition(field=status, source=Status.AGREED, target=Status.COMPLETED)
    def complete(self):
        self.completed_at = timezone.now()
