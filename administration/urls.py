from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AdminConfigurationViewSet

router = DefaultRouter()
router.register(r"config", AdminConfigurationViewSet, basename="admin-config")

urlpatterns = [
    path("", include(router.urls)),
]
