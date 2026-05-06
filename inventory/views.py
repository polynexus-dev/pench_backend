from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from core.permissions import IsERPUser
from .models import Product, Stock, Warehouse, BottleType, CustomerBottleBalance, BottleTransaction
from .serializers import (
    ProductSerializer, StockSerializer, WarehouseSerializer,
    BottleTypeSerializer, BottleTransactionSerializer
)


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all().select_related('bottle_type')
    serializer_class = ProductSerializer
    permission_classes = [IsERPUser]
    search_fields = ['name', 'sku']


class StockViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Stock.objects.select_related('product', 'warehouse')
    serializer_class = StockSerializer
    permission_classes = [IsERPUser]
    filterset_fields = ['warehouse', 'product']


class WarehouseViewSet(viewsets.ModelViewSet):
    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer
    permission_classes = [IsERPUser]


class BottleTypeViewSet(viewsets.ModelViewSet):
    queryset = BottleType.objects.all()
    serializer_class = BottleTypeSerializer
    permission_classes = [IsERPUser]


class BottleTransactionViewSet(viewsets.ModelViewSet):
    queryset = BottleTransaction.objects.select_related('bottle_type', 'customer', 'order', 'recorded_by')
    serializer_class = BottleTransactionSerializer
    permission_classes = [IsERPUser]
    filterset_fields = ['customer', 'bottle_type', 'transaction_type']


class CustomerBottleBalanceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = CustomerBottleBalance.objects.select_related('customer', 'bottle_type')
    permission_classes = [IsERPUser]
    filterset_fields = ['customer', 'bottle_type']
