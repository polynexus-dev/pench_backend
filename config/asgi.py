import os
import django
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from channels.routing import ProtocolTypeRouter, URLRouter
from core.middleware import TenantMiddleware, JWTAuthMiddleware
import tracking.routing

application = ProtocolTypeRouter(
    {
        "http": get_asgi_application(),
        "websocket": TenantMiddleware(
            JWTAuthMiddleware(URLRouter(tracking.routing.websocket_urlpatterns))
        ),
    }
)
