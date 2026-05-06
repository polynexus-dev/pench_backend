from rest_framework import serializers
from .models import (
    Product, Stock, Warehouse, BottleType, 
    CustomerBottleBalance, BottleTransaction
)


class WarehouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = ['id', 'name', 'address', 'is_active']


class BottleTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = BottleType
        fields = ['id', 'name', 'deposit_amount', 'volume_ml', 'is_active']


class ProductSerializer(serializers.ModelSerializer):
    bottle_type_name = serializers.CharField(source='bottle_type.name', read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'sku', 'description', 'unit_price', 'unit', 
            'is_active', 'bottle_type', 'bottle_type_name', 'is_returnable'
        ]


class StockSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)

    class Meta:
        model = Stock
        fields = ['id', 'product', 'product_name', 'warehouse', 'warehouse_name',
                  'quantity', 'reorder_level']


class BottleTransactionSerializer(serializers.ModelSerializer):
    bottle_type_name = serializers.CharField(source='bottle_type.name', read_only=True)
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    transaction_type_display = serializers.CharField(source='get_transaction_type_display', read_only=True)

    class Meta:
        model = BottleTransaction
        fields = [
            'id', 'bottle_type', 'bottle_type_name', 'customer', 'customer_name',
            'order', 'transaction_type', 'transaction_type_display', 'quantity',
            'notes', 'recorded_by', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class CustomerBottleBalanceSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    bottle_type_name = serializers.CharField(source='bottle_type.name', read_only=True)

    class Meta:
        model = CustomerBottleBalance
        fields = ['id', 'customer', 'customer_name', 'bottle_type', 'bottle_type_name', 'balance']
