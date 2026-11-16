from celery import shared_task
from django.contrib.gis.db.models.functions import Distance
from django.db.models import Q

from items.models import Item

from .models import Notification, Subscription
from .services import notify


def matching_subscriptions(item):
    """Подписки, условиям которых соответствует объявление. Владельцу объявления уведомление не нужно."""
    subscriptions = (
        Subscription.objects.filter(is_active=True, user__is_active=True, user__deleted_at__isnull=True)
        .exclude(user_id=item.owner_id)
        .filter(Q(item_type__isnull=True) | Q(item_type_id=item.item_type_id))
        .filter(Q(exchange_format='') | Q(exchange_format=item.exchange_format))
    )
    if item.approx_location is None:
        subscriptions = subscriptions.filter(center__isnull=True)
    else:
        subscriptions = subscriptions.annotate(distance=Distance('center', item.approx_location))

    text = f'{item.title} {item.description}'.casefold()
    for subscription in subscriptions:
        if subscription.query and subscription.query.casefold() not in text:
            continue
        distance = getattr(subscription, 'distance', None)
        if subscription.center is not None and distance.m > subscription.radius_km * 1000:
            continue
        yield subscription


@shared_task
def notify_subscribers(item_id):
    item = Item.objects.filter(pk=item_id, status=Item.Status.ACTIVE, deleted_at__isnull=True).first()
    if item is None:
        return 0
    notified = set()
    for subscription in matching_subscriptions(item):
        if subscription.user_id in notified:
            continue
        notified.add(subscription.user_id)
        notify(subscription.user_id, Notification.Type.NEW_ITEM, {
            'item_id': item.pk, 'item_title': item.title, 'subscription_id': subscription.pk,
        })
    return len(notified)
