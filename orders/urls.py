from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import OrderViewSet, RouteViewSet, DriverViewSet

router = DefaultRouter()
router.register(r"routes", RouteViewSet, basename="route")
router.register(r"driver", DriverViewSet, basename="driver-app")
router.register(r"", OrderViewSet, basename="order")

urlpatterns = [
    path("", include(router.urls)),
]
