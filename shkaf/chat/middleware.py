from http.cookies import CookieError, SimpleCookie

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication


def access_token_from(scope):
    for name, value in scope.get('headers', []):
        if name == b'cookie':
            try:
                morsel = SimpleCookie(value.decode('latin-1')).get(settings.AUTH_COOKIE_ACCESS)
            except CookieError:
                return None
            return morsel.value if morsel else None
    return None


@database_sync_to_async
def user_from_token(raw_token):
    if not raw_token:
        return AnonymousUser()
    authentication = JWTAuthentication()
    try:
        return authentication.get_user(authentication.get_validated_token(raw_token))
    except AuthenticationFailed:
        return AnonymousUser()


class JwtCookieAuthMiddleware(BaseMiddleware):
    """Определяет пользователя WebSocket по той же HttpOnly-куке access_token, что и REST API."""

    async def __call__(self, scope, receive, send):
        scope = dict(scope, user=await user_from_token(access_token_from(scope)))
        return await super().__call__(scope, receive, send)
