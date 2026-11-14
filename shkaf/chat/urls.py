from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter(trailing_slash=False)
router.register('conversations', views.ConversationViewSet, basename='conversation')

urlpatterns = router.urls
