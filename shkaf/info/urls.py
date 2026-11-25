from rest_framework.routers import SimpleRouter

from .views import ArticleViewSet

router = SimpleRouter(trailing_slash=False)
router.register('info', ArticleViewSet, basename='article')
urlpatterns = router.urls
