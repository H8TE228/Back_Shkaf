from django.db.models import Q
from django.shortcuts import get_object_or_404
from django_filters import rest_framework as django_filters
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from items.querysets import visible_items
from shkaf.pagination import StandardPagination

from . import services
from .models import Exchange
from .serializers import ExchangeSerializer


def exchanges_of(user):
    return (
        Exchange.objects.filter(Q(giver=user) | Q(receiver=user))
        .select_related('item')
        .prefetch_related('item__photos')
    )


class ExchangeFilter(django_filters.FilterSet):
    role = django_filters.ChoiceFilter(
        choices=(('giver', 'giver'), ('receiver', 'receiver')), method='filter_role',
        help_text='giver — я отдаю, receiver — я получаю',
    )

    class Meta:
        model = Exchange
        fields = ('status', 'role')

    def filter_role(self, queryset, name, value):
        return queryset.filter(**{value: self.request.user})


@extend_schema(tags=['exchanges'])
class ExchangeViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Мои передачи: где я отдаю вещь или получаю её. Видны только участникам."""

    serializer_class = ExchangeSerializer
    pagination_class = StandardPagination
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = (django_filters.DjangoFilterBackend,)
    filterset_class = ExchangeFilter
    lookup_value_regex = '[0-9]+'

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Exchange.objects.none()
        return exchanges_of(self.request.user)

    def act(self, service):
        exchange = service(self.get_object(), self.request.user)
        return Response(self.get_serializer(exchanges_of(self.request.user).get(pk=exchange.pk)).data)

    @extend_schema(request=None, responses=ExchangeSerializer)
    @action(detail=True, methods=['post'])
    def agree(self, request, pk=None):
        """Отдающий соглашается: вещь резервируется, другие заявки ждут."""
        return self.act(services.agree)

    @extend_schema(request=None, responses=ExchangeSerializer)
    @action(detail=True, methods=['post'])
    def decline(self, request, pk=None):
        """Отдающий отклоняет заявку."""
        return self.act(services.decline)

    @extend_schema(request=None, responses=ExchangeSerializer)
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Получатель отзывает заявку, или любая сторона отменяет согласованную передачу."""
        return self.act(services.cancel)

    @extend_schema(request=None, responses=ExchangeSerializer)
    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        """Сторона отмечает, что передача состоялась. После отметок обеих сторон передача завершена."""
        return self.act(services.confirm)


@extend_schema(tags=['exchanges'], parameters=[OpenApiParameter('item_id', int, OpenApiParameter.PATH)])
class ItemExchangesView(generics.ListCreateAPIView):
    """
    GET: заявки на вещь. Владелец видит все, остальные только свои.
    POST: оставить заявку на получение вещи.
    """

    serializer_class = ExchangeSerializer
    pagination_class = StandardPagination
    permission_classes = (permissions.IsAuthenticated,)

    def get_item(self):
        return get_object_or_404(visible_items(self.request.user), pk=self.kwargs['item_id'])

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Exchange.objects.none()
        return exchanges_of(self.request.user).filter(item=self.get_item())

    @extend_schema(request=None, responses={201: ExchangeSerializer})
    def post(self, request, item_id):
        exchange = services.request_exchange(self.get_item(), request.user)
        exchange = exchanges_of(request.user).get(pk=exchange.pk)
        return Response(self.get_serializer(exchange).data, status=status.HTTP_201_CREATED)
