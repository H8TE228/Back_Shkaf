from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter(trailing_slash=False)
router.register('exchanges', views.ExchangeViewSet, basename='exchange')

urlpatterns = [
    path('items/<int:item_id>/exchanges', views.ItemExchangesView.as_view(), name='item_exchanges'),
    *router.urls,
]
