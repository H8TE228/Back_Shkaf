from django.conf import settings
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.settings import api_settings


class CookieJWTAuthentication(JWTAuthentication):
    """Берёт access-токен из HttpOnly-куки."""

    def authenticate(self, request):
        raw_token = request.COOKIES.get(settings.AUTH_COOKIE_ACCESS)
        if not raw_token:
            return None
        try:
            validated_token = self.get_validated_token(raw_token)
            return self.get_user(validated_token), validated_token
        except AuthenticationFailed:
            # Устаревшая кука не должна закрывать публичные эндпоинты.
            # На защищённых эндпоинтах запрос всё равно получит 401.
            return None


class CookieJWTScheme(OpenApiAuthenticationExtension):
    target_class = 'users.authentication.CookieJWTAuthentication'
    name = 'jwtCookieAuth'
    priority = 1

    def get_security_definition(self, auto_schema):
        return {'type': 'apiKey', 'in': 'cookie', 'name': settings.AUTH_COOKIE_ACCESS}


def set_auth_cookies(response, access, refresh):
    options = {
        'httponly': True,
        'secure': settings.AUTH_COOKIE_SECURE,
        'samesite': settings.AUTH_COOKIE_SAMESITE,
    }
    response.set_cookie(
        settings.AUTH_COOKIE_ACCESS,
        access,
        max_age=int(api_settings.ACCESS_TOKEN_LIFETIME.total_seconds()),
        path=settings.AUTH_COOKIE_ACCESS_PATH,
        **options,
    )
    response.set_cookie(
        settings.AUTH_COOKIE_REFRESH,
        refresh,
        max_age=int(api_settings.REFRESH_TOKEN_LIFETIME.total_seconds()),
        path=settings.AUTH_COOKIE_REFRESH_PATH,
        **options,
    )


def clear_auth_cookies(response):
    response.delete_cookie(
        settings.AUTH_COOKIE_ACCESS,
        path=settings.AUTH_COOKIE_ACCESS_PATH,
        samesite=settings.AUTH_COOKIE_SAMESITE,
    )
    response.delete_cookie(
        settings.AUTH_COOKIE_REFRESH,
        path=settings.AUTH_COOKIE_REFRESH_PATH,
        samesite=settings.AUTH_COOKIE_SAMESITE,
    )
