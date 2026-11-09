from rest_framework.routers import SimpleRouter

from .views import ExchangePointViewSet

router = SimpleRouter(trailing_slash=False)
router.register('exchangePoints', ExchangePointViewSet, basename='exchange-point')

urlpatterns = router.urls
