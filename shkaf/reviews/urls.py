from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter(trailing_slash=False)
router.register('reviews', views.ReviewViewSet, basename='review')

urlpatterns = [
    path('users/<int:pk>/rating', views.UserRatingView.as_view(), name='user_rating'),
    *router.urls,
]
