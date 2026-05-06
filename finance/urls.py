from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import MonthlyBillViewSet

router = DefaultRouter()
router.register(r'bills', MonthlyBillViewSet, basename='bill')

urlpatterns = [
    path('', include(router.urls)),
]
