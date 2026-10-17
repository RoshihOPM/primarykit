import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
django_application = get_asgi_application()

from django.conf import settings  # noqa: E402

if "apps.realtime" in settings.INSTALLED_APPS:
    from apps.realtime.asgi import websocket_application  # noqa: E402

    async def application(scope, receive, send):
        if scope["type"] == "websocket":
            return await websocket_application(scope, receive, send)
        return await django_application(scope, receive, send)
else:
    application = django_application
