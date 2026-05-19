from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CompanyViewSet, CityViewSet, HolidayCalendarViewSet

router = DefaultRouter()
router.register(r'companies', CompanyViewSet, basename='company')
router.register(r'cities', CityViewSet, basename='city')
router.register(r'holidays', HolidayCalendarViewSet, basename='holiday')

urlpatterns = [path('', include(router.urls))]
