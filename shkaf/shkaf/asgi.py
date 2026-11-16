"""
ASGI config for shkaf project.

HTTP обслуживает Django, WebSocket — Channels (чат по вещи).
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'shkaf.settings')

# Django нужно инициализировать до импорта модулей, которые используют модели
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import OriginValidator  # noqa: E402
from django.conf import settings  # noqa: E402

from chat.middleware import JwtCookieAuthMiddleware  # noqa: E402
from chat.routing import websocket_urlpatterns as chat_routes  # noqa: E402
from notifications.routing import websocket_urlpatterns as notification_routes  # noqa: E402

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': OriginValidator(
        JwtCookieAuthMiddleware(URLRouter(chat_routes + notification_routes)),
        settings.WEBSOCKET_ALLOWED_ORIGINS,
    ),
})
