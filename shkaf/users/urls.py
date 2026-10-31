from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

urlpatterns = [
    path('login/', views.CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('login/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('register/', views.RegisterView.as_view(), name='register'),
    path('logout/', views.LogoutView.as_view(), name='logout'),

    path('profile/', views.UserProfileView.as_view(), name='user_profile'),
    path('profile/change-password/', views.ChangePasswordView.as_view(), name='change_password'),

    path('users/', views.UserListView.as_view(), name='user_list'),
]