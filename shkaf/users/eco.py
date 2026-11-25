from decimal import Decimal

from django.db.models import Count, Sum
from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, serializers
from rest_framework.response import Response

from exchanges.models import Exchange
from organizer.models import InventoryRecord

ZERO = Decimal('0.00')


class EcoStatsSerializer(serializers.Serializer):
    items_count = serializers.IntegerField()
    p2p_items_count = serializers.IntegerField()
    point_items_count = serializers.IntegerField()
    estimated_weight_kg = serializers.DecimalField(max_digits=18, decimal_places=2)
    estimated_co2_kg = serializers.DecimalField(max_digits=18, decimal_places=2)
    items_without_weight = serializers.IntegerField()
    items_without_co2_factor = serializers.IntegerField()


def contributions(user):
    exchanges = Exchange.objects.filter(giver=user, status=Exchange.Status.COMPLETED)
    for row in exchanges.values('item__item_type__avg_weight_kg', 'item__item_type__co2_per_kg').annotate(
        quantity=Count('pk'),
    ).order_by():
        yield ('p2p_items_count', row['quantity'], None, row['item__item_type__avg_weight_kg'],
               row['item__item_type__co2_per_kg'])

    intakes = InventoryRecord.objects.filter(client=user, direction=InventoryRecord.Direction.INTAKE)
    average = 'item_type__avg_weight_kg'
    factor = 'item_type__co2_per_kg'
    for row in intakes.filter(weight_kg__isnull=True).values(average, factor).annotate(
        quantity=Sum('quantity'),
    ).order_by():
        yield 'point_items_count', row['quantity'], None, row[average], row[factor]
    for row in intakes.filter(weight_kg__isnull=False).values(factor).annotate(
        quantity=Sum('quantity'), weight=Sum('weight_kg'),
    ).order_by():
        yield 'point_items_count', row['quantity'], row['weight'], None, row[factor]


def eco_stats(user):
    result = {
        'items_count': 0,
        'p2p_items_count': 0,
        'point_items_count': 0,
        'estimated_weight_kg': ZERO,
        'estimated_co2_kg': ZERO,
        'items_without_weight': 0,
        'items_without_co2_factor': 0,
    }
    for source, count, measured_weight, average_weight, co2_factor in contributions(user):
        result[source] += count
        result['items_count'] += count
        weight = measured_weight
        if weight is None and average_weight is not None and average_weight > 0:
            weight = average_weight * count
        if weight is None:
            result['items_without_weight'] += count
        else:
            result['estimated_weight_kg'] += weight
        if co2_factor is None or co2_factor < 0:
            result['items_without_co2_factor'] += count
        elif weight is not None:
            result['estimated_co2_kg'] += weight * co2_factor

    result['estimated_co2_kg'] = result['estimated_co2_kg'].quantize(ZERO)
    return result


@extend_schema(tags=['users'])
class EcoStatsView(generics.GenericAPIView):
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = EcoStatsSerializer

    def get(self, request):
        return Response(self.get_serializer(eco_stats(request.user)).data)
