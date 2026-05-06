from django.contrib import admin
from .models import Order, OrderItem, Package, Route, RouteStop

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0

class PackageInline(admin.TabularInline):
    model = Package
    extra = 0

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'customer', 'status', 'total', 'created_at']
    list_filter = ['status']
    search_fields = ['customer__name', 'delivery_address']
    inlines = [OrderItemInline, PackageInline]


class RouteStopInline(admin.TabularInline):
    model = RouteStop
    extra = 0
    raw_id_fields = ['order']

@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = ['name', 'delivery_date', 'driver', 'is_completed']
    list_filter = ['delivery_date', 'is_completed']
    inlines = [RouteStopInline]
