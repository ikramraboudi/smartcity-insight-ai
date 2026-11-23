import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from django.urls import path, re_path
from urgences.consumers import ProtectionCivileConsumer

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": URLRouter([
        path("ws/protection-civile/", ProtectionCivileConsumer.as_asgi()),
        path("ws/urgences/", ProtectionCivileConsumer.as_asgi()),
        path("ws/urgences/alertes/", ProtectionCivileConsumer.as_asgi()),
        re_path(r"^ws/urgences/.*$", ProtectionCivileConsumer.as_asgi()),
    ]),
})
