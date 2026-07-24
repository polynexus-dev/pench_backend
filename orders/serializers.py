from rest_framework import serializers
from .models import Order, OrderItem, Route, RouteStop


class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    unit_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False
    )

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "product",
            "product_name",
            "quantity",
            "unit_price",
            "line_total",
        ]


class OrderListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for Order list views — no nested items, no method field queries."""
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    zone_name = serializers.CharField(source="customer.zone.name", read_only=True, default=None)
    is_new_customer = serializers.BooleanField(source="customer.is_new", read_only=True)
    item_count = serializers.IntegerField(read_only=True, default=0)
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "customer",
            "customer_name",
            "subscription",
            "status",
            "status_display",
            "scheduled_delivery_date",
            "total",
            "items",
            "delivery_address",
            "zone_name",
            "pod_image",
            "delivered_at",
            "is_special",
            "payment_method",
            "amount_collected",
            "payment_status",
            "is_new_customer",
            "item_count",
        ]


class OrderSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    items = OrderItemSerializer(many=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    delivery_address = serializers.CharField(required=False, allow_blank=True)

    latitude = serializers.SerializerMethodField()
    longitude = serializers.SerializerMethodField()
    driver_name = serializers.SerializerMethodField()
    zone_name = serializers.SerializerMethodField()
    is_new_customer = serializers.BooleanField(source="customer.is_new", read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "customer",
            "customer_name",
            "subscription",
            "status",
            "status_display",
            "scheduled_delivery_date",
            "total",
            "items",
            "delivery_address",
            "latitude",
            "longitude",
            "driver_name",
            "zone_name",
            "pod_image",
            "pod_latitude",
            "pod_longitude",
            "delivered_at",
            "is_special",
            "payment_method",
            "amount_collected",
            "payment_transaction_id",
            "payment_status",
            "is_new_customer",
            "arriving_notification_sent",
        ]

    def get_driver_name(self, obj):
        driver = None

        # 1. Try to get driver from route stop if assigned
        try:
            if hasattr(obj, "route_stop"):
                route_stop = obj.route_stop
                if route_stop and route_stop.route:
                    driver = route_stop.route.driver
        except Exception:
            # Catch django.core.exceptions.ObjectDoesNotExist for unassigned reverse OneToOne
            pass

        # 2. If no driver from route, try fallback to customer zone driver
        if not driver:
            try:
                if (
                    obj.customer
                    and obj.customer.zone
                    and obj.customer.zone.assigned_driver
                ):
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
        if not loc:
            return None
        if hasattr(loc, "y"):
            return loc.y
        if isinstance(loc, dict):
            return loc.get("lat") or loc.get("latitude")
        return None

    def get_longitude(self, obj):
        loc = obj.customer.location
        if not loc:
            return None
        if hasattr(loc, "x"):
            return loc.x
        if isinstance(loc, dict):
            return loc.get("lng") or loc.get("longitude") or loc.get("lon")
        return None

    def create(self, validated_data):
        items_data = validated_data.pop("items")

        # Auto-fill delivery address from customer if not provided
        if not validated_data.get("delivery_address"):
            customer = validated_data.get("customer")
            if customer:
                validated_data["delivery_address"] = customer.address

        if validated_data.get("subscription") is None:
            validated_data["is_special"] = True

        order = Order.objects.create(**validated_data)

        total_amount = 0
        for item_data in items_data:
            # Auto-fill unit price from product/custom overrides if not provided
            if not item_data.get("unit_price"):
                product = item_data.get("product")
                customer = validated_data.get("customer")
                if product:
                    from inventory.models import CustomerProductPrice

                    custom_price_obj = CustomerProductPrice.objects.filter(
                        customer=customer, product=product
                    ).first()
                    if custom_price_obj:
                        item_data["unit_price"] = custom_price_obj.custom_price
                    else:
                        item_data["unit_price"] = product.unit_price

            item = OrderItem.objects.create(order=order, **item_data)
            total_amount += item.line_total

        # Update order total based on items
        order.total = total_amount
        order.save(update_fields=["total"])

        return order


class RouteStopSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="order.customer.name", read_only=True)
    customer_phone = serializers.CharField(
        source="order.customer.phone", read_only=True
    )
    customer_email = serializers.CharField(
        source="order.customer.email", read_only=True
    )
    customer_company = serializers.CharField(
        source="order.customer.company", read_only=True
    )
    customer_zone_name = serializers.CharField(
        source="order.customer.zone.name", read_only=True
    )
    address = serializers.CharField(source="order.delivery_address", read_only=True)
    order_status = serializers.SerializerMethodField()
    order_notes = serializers.CharField(source="order.delivery_notes", read_only=True)
    order_total = serializers.FloatField(source="order.total", read_only=True)
    delivered_at = serializers.DateTimeField(
        source="order.delivered_at", read_only=True
    )
    pod_image = serializers.SerializerMethodField()
    latitude = serializers.SerializerMethodField()
    longitude = serializers.SerializerMethodField()
    product_list = serializers.SerializerMethodField()
    subscription_details = serializers.SerializerMethodField()

    payment_method = serializers.CharField(
        source="order.payment_method", read_only=True
    )
    amount_collected = serializers.DecimalField(
        source="order.amount_collected", max_digits=10, decimal_places=2, read_only=True
    )
    payment_transaction_id = serializers.CharField(
        source="order.payment_transaction_id", read_only=True
    )
    payment_status = serializers.CharField(
        source="order.payment_status", read_only=True
    )

    is_new_customer = serializers.BooleanField(
        source="order.customer.is_new", read_only=True
    )

    bottles_to_deliver = serializers.SerializerMethodField()
    bottles_to_take_back = serializers.SerializerMethodField()

    class Meta:
        model = RouteStop
        fields = [
            "id",
            "sequence_number",
            "order",
            "customer_name",
            "customer_phone",
            "customer_email",
            "customer_company",
            "customer_zone_name",
            "is_new_customer",
            "address",
            "latitude",
            "longitude",
            "order_status",
            "order_notes",
            "order_total",
            "delivered_at",
            "pod_image",
            "product_list",
            "subscription_details",
            "payment_method",
            "amount_collected",
            "payment_transaction_id",
            "payment_status",
            "bottles_to_deliver",
            "bottles_to_take_back",
        ]


    def get_latitude(self, obj):
        loc = getattr(obj.order.customer, "location", None) if obj.order and obj.order.customer else None
        if not loc:
            import hashlib
            cust_id = str(obj.order.customer.id if obj.order and obj.order.customer else obj.id)
            h = int(hashlib.md5(cust_id.encode()).hexdigest(), 16)
            lat_offset = (((h % 1000) - 500) / 10000.0)
            return round(21.1458 + lat_offset, 6)
        if hasattr(loc, "y"):
            return loc.y
        if isinstance(loc, dict):
            val = loc.get("lat") or loc.get("latitude")
            if val is not None:
                return float(val)
        import hashlib
        cust_id = str(obj.order.customer.id if obj.order and obj.order.customer else obj.id)
        h = int(hashlib.md5(cust_id.encode()).hexdigest(), 16)
        lat_offset = (((h % 1000) - 500) / 10000.0)
        return round(21.1458 + lat_offset, 6)

    def get_longitude(self, obj):
        loc = getattr(obj.order.customer, "location", None) if obj.order and obj.order.customer else None
        if not loc:
            import hashlib
            cust_id = str(obj.order.customer.id if obj.order and obj.order.customer else obj.id)
            h = int(hashlib.md5(cust_id.encode()).hexdigest(), 16)
            lng_offset = ((((h // 1000) % 1000) - 500) / 10000.0)
            return round(79.0882 + lng_offset, 6)
        if hasattr(loc, "x"):
            return loc.x
        if isinstance(loc, dict):
            val = loc.get("lng") or loc.get("longitude") or loc.get("lon")
            if val is not None:
                return float(val)
        import hashlib
        cust_id = str(obj.order.customer.id if obj.order and obj.order.customer else obj.id)
        h = int(hashlib.md5(cust_id.encode()).hexdigest(), 16)
        lng_offset = ((((h // 1000) % 1000) - 500) / 10000.0)
        return round(79.0882 + lng_offset, 6)

    def get_pod_image(self, obj):
        request = self.context.get("request")
        if obj.order.pod_image and hasattr(obj.order.pod_image, "url"):
            if request:
                return request.build_absolute_uri(obj.order.pod_image.url)
            return obj.order.pod_image.url
        return None

    def get_product_list(self, obj):
        items = obj.order.items.all()
        return [
            {
                "product_id": str(item.product.id),
                "product_name": item.product.name,
                "quantity": item.quantity,
                "unit": item.product.unit,
                "unit_price": float(item.unit_price),
            }
            for item in items
        ]

    def get_subscription_details(self, obj):
        # 1. If today's order was generated from a subscription, show it directly
        sub = obj.order.subscription

        # 2. Fallback: If not linked but the customer has an active subscription, show it
        if not sub:
            from subscriptions.models import Subscription, SubscriptionStatus

            customer = obj.order.customer
            if customer and hasattr(customer, "_prefetched_objects_cache") and "subscriptions" in customer._prefetched_objects_cache:
                active_subs = [s for s in customer.subscriptions.all() if s.status == SubscriptionStatus.ACTIVE]
                sub = active_subs[0] if active_subs else None
            else:
                sub = Subscription.objects.filter(
                    customer=obj.order.customer, status=SubscriptionStatus.ACTIVE
                ).first()

        if sub:
            items = sub.items.all()
            return {
                "id": str(sub.id),
                "frequency": sub.get_frequency_display(),
                "is_paused": sub.is_paused,
                "special_instructions": sub.special_instructions,
                "items": [
                    {
                        "product_name": item.product.name,
                        "quantity": item.quantity,
                        "unit": item.product.unit,
                    }
                    for item in items
                ],
            }
        return None

    def get_order_status(self, obj):
        # If route is started/in progress, return 'in_transit' for active order statuses
        from orders.models import RouteStatus, OrderStatus

        status = obj.order.status
        if status == "in_progress":
            return "in_transit"
        if obj.route and (
            obj.route.status == RouteStatus.IN_PROGRESS
            or obj.route.status == "in_transit"
            or obj.route.started_at is not None
        ):
            if status in [
                OrderStatus.PENDING,
                OrderStatus.CONFIRMED,
                OrderStatus.DISPATCHED,
            ]:
                return "in_transit"
        return status

    def get_bottles_to_deliver(self, obj):
        from collections import defaultdict
        bottle_counts = defaultdict(int)
        bottle_names = {}
        bottle_volumes = {}
        for item in obj.order.items.all():
            product = item.product
            if product.is_returnable and product.bottle_type:
                bt = product.bottle_type
                bottle_counts[bt.id] += item.quantity
                bottle_names[bt.id] = bt.name
                bottle_volumes[bt.id] = bt.volume_ml
        
        return [
            {
                "bottle_type_id": str(bt_id),
                "bottle_type_name": bottle_names[bt_id],
                "quantity": qty,
                "value": 0.5 if bottle_volumes[bt_id] == 500 else (1.0 if bottle_volumes[bt_id] == 1000 else float(bottle_volumes[bt_id]) / 1000.0)
            }
            for bt_id, qty in bottle_counts.items()
        ]

    def get_bottles_to_take_back(self, obj):
        from inventory.models import CustomerBottleBalance
        balances = CustomerBottleBalance.objects.filter(customer=obj.order.customer).select_related("bottle_type")
        return [
            {
                "bottle_type_id": str(bal.bottle_type.id),
                "bottle_type_name": bal.bottle_type.name,
                "quantity": bal.balance,
                "value": 0.5 if bal.bottle_type.volume_ml == 500 else (1.0 if bal.bottle_type.volume_ml == 1000 else float(bal.bottle_type.volume_ml) / 1000.0)
            }
            for bal in balances
        ]



class RouteSerializer(serializers.ModelSerializer):
    stops = RouteStopSerializer(many=True, read_only=True)
    driver_name = serializers.CharField(source="driver.get_full_name", read_only=True)
    route_id = serializers.CharField(source="id", read_only=True)
    status = serializers.SerializerMethodField()

    # Return geometry as GeoJSON
    route_geometry = serializers.SerializerMethodField()
    dispatch_bottles_1L = serializers.SerializerMethodField()
    dispatch_bottles_500ml = serializers.SerializerMethodField()

    additional_driver_names = serializers.SerializerMethodField()

    company_upi_id = serializers.SerializerMethodField()
    company_upi_name = serializers.SerializerMethodField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from accounts.models import User

        self.fields["additional_drivers"] = serializers.PrimaryKeyRelatedField(
            many=True, queryset=User.objects.all(), required=False
        )

    def get_status(self, obj):
        if obj.status == "in_progress":
            return "in_transit"
        return obj.status

    def get_additional_driver_names(self, obj):
        return [
            drv.get_full_name() or drv.username for drv in obj.additional_drivers.all()
        ]

    def get_company_upi_id(self, obj):
        from administration.models import AdminConfiguration
        return AdminConfiguration.get_solo().company_upi_id

    def get_company_upi_name(self, obj):
        from administration.models import AdminConfiguration
        config = AdminConfiguration.get_solo()
        return config.company_upi_name or config.company_name

    class Meta:
        model = Route
        fields = [
            "id",
            "route_id",
            "name",
            "driver",
            "driver_name",
            "delivery_date",
            "status",
            "is_locked",
            "is_completed",
            "route_geometry",
            "stops",
            "dispatch_bottles_1L",
            "dispatch_bottles_500ml",
            "additional_drivers",
            "additional_driver_names",
            "company_upi_id",
            "company_upi_name",
            "actual_distance_km",
            "stoppage_duration_minutes",
            "actual_duration_minutes",
            "stoppage_history",
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


class RouteListSerializer(serializers.ModelSerializer):
    """Serializer for Route list views — includes full stops array so route cards and customer lists render seamlessly."""
    driver_name = serializers.CharField(source="driver.get_full_name", read_only=True)
    route_id = serializers.CharField(source="id", read_only=True)
    stops_count = serializers.IntegerField(read_only=True, default=0)
    total_stops = serializers.IntegerField(source="stops_count", read_only=True, default=0)
    stops = RouteStopSerializer(many=True, read_only=True)

    class Meta:
        model = Route
        fields = [
            "id",
            "route_id",
            "name",
            "driver",
            "driver_name",
            "delivery_date",
            "status",
            "is_locked",
            "is_completed",
            "stops_count",
            "total_stops",
            "stops",
            "actual_distance_km",
            "stoppage_duration_minutes",
            "actual_duration_minutes",
        ]


