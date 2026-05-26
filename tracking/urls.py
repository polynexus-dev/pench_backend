from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DriverLocationViewSet

router = DefaultRouter()
router.register(r"live", DriverLocationViewSet, basename="live-location")

urlpatterns = [
    path("", include(router.urls)),
]
