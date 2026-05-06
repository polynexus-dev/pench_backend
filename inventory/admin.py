from django.contrib import admin
from .models import (
    Product, Stock, Warehouse, BottleType, 
    CustomerBottleBalance, BottleTransaction
)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'sku', 'unit_price', 'unit', 'bottle_type', 'is_returnable', 'is_active']
    list_filter = ['is_returnable', 'is_active', 'bottle_type']
    search_fields = ['name', 'sku']

@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = ['product', 'warehouse', 'quantity', 'reorder_level']
    list_filter = ['warehouse']

@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active']
    list_filter = ['is_active']

@admin.register(BottleType)
class BottleTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'deposit_amount', 'volume_ml', 'is_active']

@admin.register(CustomerBottleBalance)
class CustomerBottleBalanceAdmin(admin.ModelAdmin):
    list_display = ['customer', 'bottle_type', 'balance']
    list_filter = ['bottle_type']
    search_fields = ['customer__name']

@admin.register(BottleTransaction)
class BottleTransactionAdmin(admin.ModelAdmin):
    list_display = ['bottle_type', 'customer', 'transaction_type', 'quantity', 'created_at']
    list_filter = ['transaction_type', 'bottle_type']
    search_fields = ['customer__name', 'notes']
