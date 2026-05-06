from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import RouteViewSet, DriverViewSet, TrackingEventViewSet, DailyReconciliationViewSet

router = DefaultRouter()
router.register(r'routes', RouteViewSet, basename='route')
router.register(r'drivers', DriverViewSet, basename='driver')
router.register(r'tracking', TrackingEventViewSet, basename='tracking')
router.register(r'reconciliations', DailyReconciliationViewSet, basename='reconciliation')

urlpatterns = [
    path('', include(router.urls)),
]
