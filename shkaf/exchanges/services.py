"""
Сценарии передачи вещи. Каждый выполняется в одной транзакции с блокировкой строк вещи и передачи,
поэтому два одновременных согласия на одну вещь не пройдут.
"""
from django.db import IntegrityError, transaction
from django.utils import timezone
from django_fsm import TransitionNotAllowed
from rest_framework.exceptions import PermissionDenied, ValidationError

from items.exceptions import StateConflict
from items.models import Item
from notifications.models import Notification
from notifications.services import exchange_payload, notify

from .models import Exchange


def _locked(exchange):
    item = Item.objects.select_for_update().get(pk=exchange.item_id)
    return Exchange.objects.select_for_update().get(pk=exchange.pk), item


def _apply(transition_method):
    try:
        transition_method()
    except TransitionNotAllowed:
        raise StateConflict('This action is not allowed in the current exchange status.') from None


@transaction.atomic
def request_exchange(item, receiver):
    item = Item.objects.select_for_update().get(pk=item.pk)
    if item.owner_id == receiver.pk:
        raise ValidationError({'item': 'You cannot request your own item.'})
    if item.status != Item.Status.ACTIVE:
        raise StateConflict('The item is not available for exchange.')
    try:
        with transaction.atomic():
            exchange = Exchange.objects.create(item=item, giver_id=item.owner_id, receiver=receiver)
    except IntegrityError:
        raise StateConflict('You already have an open request for this item.') from None
    notify(exchange.giver_id, Notification.Type.EXCHANGE_REQUESTED, exchange_payload(exchange))
    return exchange


@transaction.atomic
def agree(exchange, user):
    exchange, item = _locked(exchange)
    if user.pk != exchange.giver_id:
        raise PermissionDenied('Only the giver can accept a request.')
    if item.status != Item.Status.ACTIVE:
        raise StateConflict('The item is already reserved or given.')
    _apply(exchange.agree)
    item.status = Item.Status.RESERVED
    try:
        with transaction.atomic():
            exchange.save()
    except IntegrityError:
        raise StateConflict('The item is already reserved.') from None
    item.save(update_fields=['status', 'updated_at'])
    notify(exchange.receiver_id, Notification.Type.EXCHANGE_AGREED, exchange_payload(exchange))
    return exchange


@transaction.atomic
def decline(exchange, user):
    exchange, _ = _locked(exchange)
    if user.pk != exchange.giver_id:
        raise PermissionDenied('Only the giver can decline a request.')
    _apply(exchange.decline)
    exchange.save()
    notify(exchange.receiver_id, Notification.Type.EXCHANGE_DECLINED, exchange_payload(exchange))
    return exchange


@transaction.atomic
def cancel(exchange, user):
    exchange, item = _locked(exchange)
    role = exchange.participant_role(user)
    if role is None:
        raise PermissionDenied()
    if exchange.status == Exchange.Status.REQUESTED and role != 'receiver':
        raise PermissionDenied('The giver declines a request instead of cancelling it.')
    was_agreed = exchange.status == Exchange.Status.AGREED
    _apply(exchange.cancel)
    exchange.save()
    if was_agreed and item.status == Item.Status.RESERVED:
        item.status = Item.Status.ACTIVE
        item.save(update_fields=['status', 'updated_at'])
    other_side = exchange.receiver_id if role == 'giver' else exchange.giver_id
    notify(other_side, Notification.Type.EXCHANGE_CANCELLED, exchange_payload(exchange))
    return exchange


@transaction.atomic
def confirm(exchange, user):
    """Каждая сторона отмечает факт передачи. Когда отметили обе, передача завершается."""
    exchange, item = _locked(exchange)
    role = exchange.participant_role(user)
    if role is None:
        raise PermissionDenied()
    if exchange.status != Exchange.Status.AGREED:
        raise StateConflict('Only an agreed exchange can be confirmed.')
    field = f'{role}_confirmed_at'
    if getattr(exchange, field) is None:
        setattr(exchange, field, timezone.now())
    if exchange.giver_confirmed_at and exchange.receiver_confirmed_at:
        _apply(exchange.complete)
        item.status = Item.Status.GIVEN
        item.save(update_fields=['status', 'updated_at'])
        decline_open_requests(item, exclude=exchange)
    exchange.save()
    if exchange.status == Exchange.Status.COMPLETED:
        for user_id in (exchange.giver_id, exchange.receiver_id):
            notify(user_id, Notification.Type.EXCHANGE_COMPLETED, exchange_payload(exchange))
    return exchange


def decline_open_requests(item, exclude=None):
    """Отклоняет ожидающие заявки, когда вещь передана, ушла в архив или удалена."""
    requests = Exchange.objects.filter(item=item, status=Exchange.Status.REQUESTED).select_related('item')
    if exclude is not None:
        requests = requests.exclude(pk=exclude.pk)
    declined = list(requests)
    Exchange.objects.filter(pk__in=[e.pk for e in declined]).update(
        status=Exchange.Status.DECLINED, updated_at=timezone.now()
    )
    for exchange in declined:
        notify(exchange.receiver_id, Notification.Type.EXCHANGE_DECLINED, exchange_payload(exchange))
    return len(declined)
