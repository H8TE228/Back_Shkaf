from django.db.models import Q

from .models import Item

PUBLIC_STATUSES = (Item.Status.ACTIVE, Item.Status.RESERVED, Item.Status.GIVEN)


def existing_items():
    return (
        Item.objects
        .filter(deleted_at__isnull=True, owner__deleted_at__isnull=True)
        .select_related('item_type')
        .prefetch_related('photos')
        .order_by('-created_at', '-pk')
    )


def visible_items(user):
    visible = Q(status__in=PUBLIC_STATUSES)
    if user.is_authenticated:
        visible |= Q(owner=user)
    return existing_items().filter(visible)
