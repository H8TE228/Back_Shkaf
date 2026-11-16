from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter(trailing_slash=False)
router.register('me/subscriptions', views.SubscriptionViewSet, basename='subscription')
router.register('me/notifications', views.NotificationViewSet, basename='notification')

urlpatterns = router.urls
