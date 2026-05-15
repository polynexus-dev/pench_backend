from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CityViewSet, HolidayCalendarViewSet

router = DefaultRouter()
router.register(r'cities', CityViewSet, basename='city')
router.register(r'holidays', HolidayCalendarViewSet, basename='holiday')

urlpatterns = [path('', include(router.urls))]
