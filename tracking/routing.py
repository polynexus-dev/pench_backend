from django.urls import path
from .consumers import TrackingConsumer

websocket_urlpatterns = [
    path("ws/tracking/", TrackingConsumer.as_asgi()),
    path("ws/tracking/driver/<str:driver_id>/", TrackingConsumer.as_asgi()),
]
