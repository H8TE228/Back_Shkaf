from django.conf import settings
from django.db import models
from django.db.models.functions import Length
from django.db.models.lookups import GreaterThan, LessThanOrEqual
from django.utils.translation import gettext_lazy as _

MAX_MESSAGE_LENGTH = 4000


class Conversation(models.Model):
    """Диалог по вещи между владельцем и откликнувшимся (ERD v2)."""

    item = models.ForeignKey(
        'items.Item', on_delete=models.PROTECT, related_name='conversations', verbose_name=_('item')
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='owned_conversations',
        verbose_name=_('owner'),
    )
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='requested_conversations',
        verbose_name=_('requester'),
    )
    created_at = models.DateTimeField(_('creation date'), auto_now_add=True)

    class Meta:
        verbose_name = _('conversation')
        verbose_name_plural = _('conversations')
        constraints = [
            models.UniqueConstraint(fields=['item', 'requester'], name='conversation_item_requester_unique'),
            models.CheckConstraint(
                condition=~models.Q(owner=models.F('requester')), name='conversation_participants_differ'
            ),
        ]

    def __str__(self):
        return f'{self.item} ({self.requester})'


class Message(models.Model):
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name='messages', verbose_name=_('conversation')
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='messages', verbose_name=_('sender')
    )
    body = models.TextField(_('body'))
    read_at = models.DateTimeField(_('read date'), null=True, blank=True)
    created_at = models.DateTimeField(_('creation date'), auto_now_add=True)

    class Meta:
        verbose_name = _('message')
        verbose_name_plural = _('messages')
        indexes = [models.Index(fields=['conversation', 'created_at'])]
        constraints = [
            models.CheckConstraint(
                condition=LessThanOrEqual(Length('body'), MAX_MESSAGE_LENGTH), name='message_body_max_length'
            ),
            models.CheckConstraint(condition=GreaterThan(Length('body'), 0), name='message_body_not_empty'),
        ]

    def __str__(self):
        return f'{self.sender}: {self.body[:30]}'
