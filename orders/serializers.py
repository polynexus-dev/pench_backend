from rest_framework import serializers
from .models import Order, OrderItem, Route, RouteStop


class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)

    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)

    class Meta:
        model = OrderItem
        fields = ['id', 'product', 'product_name', 'quantity', 'unit_price', 'line_total']


class OrderSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    items = OrderItemSerializer(many=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    delivery_address = serializers.CharField(required=False, allow_blank=True)
    
    latitude = serializers.SerializerMethodField()
    longitude = serializers.SerializerMethodField()
    driver_name = serializers.SerializerMethodField()
    zone_name = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id', 'customer', 'customer_name', 'status', 'status_display',
            'scheduled_delivery_date', 'total', 'items', 'delivery_address',
            'latitude', 'longitude', 'driver_name', 'zone_name',
            'pod_image', 'pod_latitude', 'pod_longitude', 'delivered_at'
        ]

    def get_driver_name(self, obj):
        driver = None
        
        # 1. Try to get driver from route stop if assigned
        try:
            if hasattr(obj, 'route_stop'):
                route_stop = obj.route_stop
                if route_stop and route_stop.route:
                    driver = route_stop.route.driver
        except Exception:
            # Catch django.core.exceptions.ObjectDoesNotExist for unassigned reverse OneToOne
            pass

        # 2. If no driver from route, try fallback to customer zone driver
        if not driver:
            try:
                if obj.customer and obj.customer.zone and obj.customer.zone.assigned_driver:
                    driver = obj.customer.zone.assigned_driver
            except Exception:
                pass

        # 3. Format driver name if found
        if driver:
            try:
                full_name = driver.get_full_name()
                if full_name.strip():
                    return full_name
                return driver.username
            except Exception:
                pass

        return None

    def get_zone_name(self, obj):
        try:
            if obj.customer and obj.customer.zone:
                return obj.customer.zone.name
        except Exception:
            pass
        return None

    def get_latitude(self, obj):
        loc = obj.customer.location
        if not loc: return None
        if hasattr(loc, 'y'): return loc.y
        if isinstance(loc, dict): return loc.get('lat') or loc.get('latitude')
        return None

    def get_longitude(self, obj):
        loc = obj.customer.location
        if not loc: return None
        if hasattr(loc, 'x'): return loc.x
        if isinstance(loc, dict): return loc.get('lng') or loc.get('longitude') or loc.get('lon')
        return None

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        
        # Auto-fill delivery address from customer if not provided
        if not validated_data.get('delivery_address'):
            customer = validated_data.get('customer')
            if customer:
                validated_data['delivery_address'] = customer.address
        
        order = Order.objects.create(**validated_data)
        
        total_amount = 0
        for item_data in items_data:
            # Auto-fill unit price from product/custom overrides if not provided
            if not item_data.get('unit_price'):
                product = item_data.get('product')
                customer = validated_data.get('customer')
                if product:
                    from inventory.models import CustomerProductPrice
                    custom_price_obj = CustomerProductPrice.objects.filter(customer=customer, product=product).first()
                    if custom_price_obj:
                        item_data['unit_price'] = custom_price_obj.custom_price
                    else:
                        item_data['unit_price'] = product.unit_price
            
            item = OrderItem.objects.create(order=order, **item_data)
            total_amount += item.line_total
            
        # Update order total based on items
        order.total = total_amount
        order.save(update_fields=['total'])
        
        return order


class RouteStopSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='order.customer.name', read_only=True)
    address = serializers.CharField(source='order.delivery_address', read_only=True)
    latitude = serializers.SerializerMethodField()
    longitude = serializers.SerializerMethodField()
    order_status = serializers.CharField(source='order.status', read_only=True)

    class Meta:
        model = RouteStop
        fields = ['id', 'sequence_number', 'order', 'customer_name', 'address', 'latitude', 'longitude', 'order_status']

    def get_latitude(self, obj):
        loc = obj.order.customer.location
        if not loc: return None
        if hasattr(loc, 'y'): return loc.y
        if isinstance(loc, dict): return loc.get('lat') or loc.get('latitude')
        return None

    def get_longitude(self, obj):
        loc = obj.order.customer.location
        if not loc: return None
        if hasattr(loc, 'x'): return loc.x
        if isinstance(loc, dict): return loc.get('lng') or loc.get('longitude') or loc.get('lon')
        return None


class RouteSerializer(serializers.ModelSerializer):
    stops = RouteStopSerializer(many=True, read_only=True)
    driver_name = serializers.CharField(source='driver.get_full_name', read_only=True)
    
    # Return geometry as GeoJSON
    route_geometry = serializers.SerializerMethodField()
    dispatch_bottles_1L = serializers.SerializerMethodField()
    dispatch_bottles_500ml = serializers.SerializerMethodField()

    class Meta:
        model = Route
        fields = [
            'id', 'name', 'driver', 'driver_name', 'delivery_date', 
            'is_completed', 'route_geometry', 'stops',
            'dispatch_bottles_1L', 'dispatch_bottles_500ml'
        ]

    def get_route_geometry(self, obj):
        if not obj.geometry:
            return None
        # Convert Point list to simple list of coords for frontend
        return [[p[0], p[1]] for p in obj.geometry.coords]

    def get_dispatch_bottles_1L(self, obj):
        total = 0
        try:
            for stop in obj.stops.all():
                for item in stop.order.items.all():
                    product = item.product
                    if product.bottle_type and product.bottle_type.volume_ml == 1000:
                        total += item.quantity
        except Exception:
            pass
        return total

    def get_dispatch_bottles_500ml(self, obj):
        total = 0
        try:
            for stop in obj.stops.all():
                for item in stop.order.items.all():
                    product = item.product
                    if product.bottle_type and product.bottle_type.volume_ml == 500:
                        total += item.quantity
        except Exception:
            pass
        return total
