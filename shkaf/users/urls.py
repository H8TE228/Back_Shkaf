from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

urlpatterns = [
    path('register', views.RegisterView.as_view(), name='register'),
    path('auth', views.CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/refresh', TokenRefreshView.as_view(), name='token_refresh'),
    path('logout', views.LogoutView.as_view(), name='logout'),

    path('', views.UserListView.as_view(), name='user_list'),
    path('<int:pk>', views.UserDetailView.as_view(), name='user_detail'),
]
