from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CompanyViewSet, CityViewSet, HolidayCalendarViewSet, EraseAllDataView
from routing.views import ZoneViewSet

router = DefaultRouter()
router.register(r"companies", CompanyViewSet, basename="company")
router.register(r"cities", CityViewSet, basename="city")
router.register(r"holidays", HolidayCalendarViewSet, basename="holiday")
router.register(r"zones", ZoneViewSet, basename="zone")

urlpatterns = [
    path("erase-all/", EraseAllDataView.as_view(), name="erase-all-data"),
    path("", include(router.urls)),
]
