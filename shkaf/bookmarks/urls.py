from django.urls import path

from .views import ItemBookmarkView, MyBookmarksView, PointBookmarkView

urlpatterns = [
    path('me/bookmarks', MyBookmarksView.as_view(), name='my-bookmarks'),
    path('items/<int:pk>/bookmark', ItemBookmarkView.as_view(), name='item-bookmark'),
    path('exchangePoints/<int:pk>/bookmark', PointBookmarkView.as_view(), name='point-bookmark'),
]
