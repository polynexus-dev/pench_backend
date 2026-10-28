from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import MonthlyBillViewSet, TransactionViewSet, OnlinePaymentViewSet

router = DefaultRouter()
router.register(r"bills", MonthlyBillViewSet, basename="bill")
router.register(r"transactions", TransactionViewSet, basename="transaction")
router.register(r"online-payments", OnlinePaymentViewSet, basename="online-payment")

urlpatterns = [
    path("", include(router.urls)),
]
