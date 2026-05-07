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

    def create(self, request, *args, **kwargs):
        """
        Supports creating multiple products in a single POST request.
        """
        is_many = isinstance(request.data, list)
        if not is_many:
            return super().create(request, *args, **kwargs)
        
        serializer = self.get_serializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=False, methods=['patch', 'put'])
    def bulk_update(self, request):
        """
        Updates multiple products at once. Each object must have an 'id'.
        """
        data = request.data
        if not isinstance(data, list):
            return Response({"detail": "Expected a list of objects."}, status=status.HTTP_400_BAD_REQUEST)

        updated_products = []
        for item in data:
            product_id = item.get('id')
            if not product_id:
                continue
            
            try:
                instance = Product.objects.get(id=product_id)
                serializer = self.get_serializer(instance, data=item, partial=True)
                serializer.is_valid(raise_exception=True)
                serializer.save()
                updated_products.append(serializer.data)
            except Product.DoesNotExist:
                continue

        return Response(updated_products, status=status.HTTP_200_OK)


class StockViewSet(viewsets.ModelViewSet):
    queryset = Stock.objects.select_related('product', 'warehouse')
    serializer_class = StockSerializer
    permission_classes = [IsERPUser]
    filterset_fields = ['warehouse', 'product']

    @action(detail=False, methods=['patch', 'put'])
    def bulk_update(self, request):
        """
        Updates stock levels for multiple items. Each object must have an 'id'.
        """
        data = request.data
        if not isinstance(data, list):
            return Response({"detail": "Expected a list."}, status=status.HTTP_400_BAD_REQUEST)

        updated = []
        for item in data:
            stock_id = item.get('id')
            if not stock_id: continue
            try:
                instance = Stock.objects.get(id=stock_id)
                serializer = self.get_serializer(instance, data=item, partial=True)
                serializer.is_valid(raise_exception=True)
                serializer.save()
                updated.append(serializer.data)
            except Stock.DoesNotExist:
                continue
        return Response(updated, status=status.HTTP_200_OK)


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

    def create(self, request, *args, **kwargs):
        """
        Supports bulk logging of bottle transactions.
        """
        is_many = isinstance(request.data, list)
        if not is_many:
            return super().create(request, *args, **kwargs)
        
        serializer = self.get_serializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class CustomerBottleBalanceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = CustomerBottleBalance.objects.select_related('customer', 'bottle_type')
    permission_classes = [IsERPUser]
    filterset_fields = ['customer', 'bottle_type']
