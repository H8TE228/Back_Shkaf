from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from users.views import ChangePasswordView, MeView

urlpatterns = [
    path('admin/', admin.site.urls),

    path('api/v1/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/v1/schema/', SpectacularAPIView.as_view(), name='schema'),

    path('api/v1/users/', include('users.urls')),
    path('api/v1/me', MeView.as_view(), name='me'),
    path('api/v1/me/change-password', ChangePasswordView.as_view(), name='change_password'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)