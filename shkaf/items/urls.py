from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter(trailing_slash=False)
router.register('items', views.ItemViewSet, basename='item')
router.register('itemTypes', views.ItemTypeViewSet, basename='item-type')

urlpatterns = router.urls
