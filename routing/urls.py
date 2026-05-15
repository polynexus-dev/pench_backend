from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    RouteViewSet, DriverViewSet, TrackingEventViewSet, 
    DailyReconciliationViewSet, ZoneViewSet
)

router = DefaultRouter()
router.register(r'zones', ZoneViewSet, basename='zone')
router.register(r'routes', RouteViewSet, basename='route')
router.register(r'drivers', DriverViewSet, basename='driver')
router.register(r'tracking', TrackingEventViewSet, basename='tracking')
router.register(r'reconciliations', DailyReconciliationViewSet, basename='reconciliation')

urlpatterns = [
    path('', include(router.urls)),
]
