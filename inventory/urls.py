from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ProductViewSet, StockViewSet, WarehouseViewSet, 
    BottleTypeViewSet, BottleTransactionViewSet, CustomerBottleBalanceViewSet,
    CustomerProductPriceViewSet
)

router = DefaultRouter()
router.register(r'products', ProductViewSet, basename='product')
router.register(r'stock', StockViewSet, basename='stock')
router.register(r'warehouses', WarehouseViewSet, basename='warehouse')
router.register(r'bottle-types', BottleTypeViewSet, basename='bottle-type')
router.register(r'bottle-transactions', BottleTransactionViewSet, basename='bottle-transaction')
router.register(r'bottle-balances', CustomerBottleBalanceViewSet, basename='bottle-balance')
router.register(r'customer-prices', CustomerProductPriceViewSet, basename='customer-price')

urlpatterns = [path('', include(router.urls))]
