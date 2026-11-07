from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    MonthlyBillViewSet,
    TransactionViewSet,
    OnlinePaymentViewSet,
    PayUInitiateView,
    PayUCallbackView,
    PayUWebhookView,
    PayUMobileHashView,
    PayUPaymentStatusView,
    PayUSandboxTestPageView,
    HandlingFeeSlabsView,
)

router = DefaultRouter()
router.register(r"bills", MonthlyBillViewSet, basename="bill")
router.register(r"transactions", TransactionViewSet, basename="transaction")
router.register(r"online-payments", OnlinePaymentViewSet, basename="online-payment")

urlpatterns = [
    path("handling-fee-slabs/", HandlingFeeSlabsView.as_view(), name="handling-fee-slabs"),
    path("payu/initiate/", PayUInitiateView.as_view(), name="payu-initiate"),
    path("payu/callback/", PayUCallbackView.as_view(), name="payu-callback"),
    path("payu/webhook/", PayUWebhookView.as_view(), name="payu-webhook"),
    path("payu/mobile-hash/", PayUMobileHashView.as_view(), name="payu-mobile-hash"),
    path("payu/status/<str:txnid>/", PayUPaymentStatusView.as_view(), name="payu-status"),
    path("payu/sandbox-test/", PayUSandboxTestPageView.as_view(), name="payu-sandbox-test"),
    path("", include(router.urls)),
]
