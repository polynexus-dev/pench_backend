from rest_framework import serializers
from .models import Order, OrderItem, Route, RouteStop


class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = OrderItem
        fields = ['id', 'product', 'product_name', 'quantity', 'unit_price', 'line_total']


class OrderSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    items = OrderItemSerializer(many=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    latitude = serializers.FloatField(source='customer.location.y', read_only=True)
    longitude = serializers.FloatField(source='customer.location.x', read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'customer', 'customer_name', 'status', 'status_display',
            'scheduled_delivery_date', 'total', 'items', 'delivery_address',
            'latitude', 'longitude'
        ]

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        order = Order.objects.create(**validated_data)
        for item_data in items_data:
            OrderItem.objects.create(order=order, **item_data)
        return order


class RouteStopSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='order.customer.name', read_only=True)
    address = serializers.CharField(source='order.delivery_address', read_only=True)
    latitude = serializers.FloatField(source='order.customer.location.y', read_only=True)
    longitude = serializers.FloatField(source='order.customer.location.x', read_only=True)

    class Meta:
        model = RouteStop
        fields = ['id', 'sequence_number', 'order', 'customer_name', 'address', 'latitude', 'longitude']


class RouteSerializer(serializers.ModelSerializer):
    stops = RouteStopSerializer(many=True, read_only=True)
    driver_name = serializers.CharField(source='driver.get_full_name', read_only=True)
    
    # Return geometry as GeoJSON
    route_geometry = serializers.SerializerMethodField()

    class Meta:
        model = Route
        fields = [
            'id', 'name', 'driver', 'driver_name', 'delivery_date', 
            'is_completed', 'route_geometry', 'stops'
        ]

    def get_route_geometry(self, obj):
        if not obj.geometry:
            return None
        # Convert Point list to simple list of coords for frontend
        return [[p[0], p[1]] for p in obj.geometry.coords]
