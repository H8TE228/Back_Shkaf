from django.urls import path

from . import views

urlpatterns = [
    path('register', views.RegisterView.as_view(), name='register'),
    path('login', views.LoginView.as_view(), name='login'),
    path('login/refresh', views.RefreshView.as_view(), name='token_refresh'),
    path('logout', views.LogoutView.as_view(), name='logout'),

    path('', views.UserListView.as_view(), name='user_list'),
    path('<int:pk>', views.UserDetailView.as_view(), name='user_detail'),
]
