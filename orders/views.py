from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from core.permissions import IsERPUser, HasGroupPermission
from .models import Order, OrderStatus, Route
from .serializers import OrderSerializer, RouteSerializer
from .services import create_optimized_route
from orders.services.route_generator import (
    generate_daily_routes_for_date,
    regenerate_daily_routes_for_date,
)
from orders.services.trip_management import (
    lock_route_for_trip,
    unlock_route_for_trip,
    start_trip_for_route,
    stop_trip_for_route,
)
import datetime


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.select_related(
        "customer__zone__assigned_driver", "route_stop__route__driver"
    ).prefetch_related("items__product")
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]  # Base permission is just authenticated
    filterset_fields = ["status", "customer", "scheduled_delivery_date"]

    def get_permissions(self):
        """
        ERP users can do everything. Customers can list, retrieve, create, update, and destroy their own orders.
        """
        if self.action in ["list", "retrieve", "create", "partial_update", "update", "destroy", "special_orders"]:
            return [IsAuthenticated()]
        # Management actions require ERP permissions
        return [IsERPUser(), HasGroupPermission()]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        # If user is ERP Admin/Manager, show all
        if user.is_erp_user or user.is_superuser:
            return qs

        # Otherwise, if they have a customer profile, show only their orders
        if hasattr(user, "customer_profile"):
            return qs.filter(customer=user.customer_profile)

        # Allow drivers to access orders assigned to their routes (primary or additional driver)
        from .models import RouteStop
        from django.db.models import Q

        assigned_order_ids = (
            RouteStop.objects.filter(
                Q(route__driver=user) | Q(route__additional_drivers=user)
            )
            .distinct()
            .values_list("order_id", flat=True)
        )
        if assigned_order_ids.exists() or getattr(user, "is_driver", False):
            return qs.filter(id__in=assigned_order_ids)

        # Fallback for other roles: no orders unless they are ERP users
        return qs.none()

    def create(self, request, *args, **kwargs):
        """
        Supports creating multiple orders in one request.
        For customers, we auto-fill and enforce that they only create orders for themselves.
        Enforces that they cannot place a same-day order if today's delivery route has already departed (is in_progress or completed).
        """
        user = request.user
        is_customer = hasattr(user, "customer_profile") and user.customer_profile is not None

        if is_customer:
            import datetime
            from rest_framework.exceptions import ValidationError
            from routing.models import Route, RouteStatus
            
            data_list = request.data if isinstance(request.data, list) else [request.data]
            for item in data_list:
                date_str = item.get("scheduled_delivery_date")
                if date_str:
                    try:
                        delivery_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                    except ValueError:
                        continue
                    
                    if delivery_date == datetime.date.today():
                        active_routes = Route.objects.filter(
                            delivery_date=delivery_date,
                            orders__customer=user.customer_profile,
                            status__in=[RouteStatus.IN_PROGRESS, RouteStatus.COMPLETED]
                        )
                        if active_routes.exists():
                            raise ValidationError(
                                "Cannot place order for today: Your delivery route for today has already departed (in transit/completed)."
                            )

            if isinstance(request.data, list):
                for item in request.data:
                    item["customer"] = user.customer_profile.id
            else:
                if hasattr(request.data, "_mutable"):
                    request.data._mutable = True
                request.data["customer"] = user.customer_profile.id

        is_many = isinstance(request.data, list)
        if not is_many:
            return super().create(request, *args, **kwargs)

        serializer = self.get_serializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def perform_create(self, serializer):
        serializer.save()
        orders = serializer.instance
        if not isinstance(orders, list):
            orders = [orders]

        from orders.services.route_generator import add_order_to_active_route_if_pending
        for order in orders:
            try:
                add_order_to_active_route_if_pending(order)
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed calling add_order_to_active_route_if_pending: {str(e)}")

    def update(self, request, *args, **kwargs):
        user = request.user
        is_customer = hasattr(user, "customer_profile") and user.customer_profile is not None
        if is_customer:
            instance = self.get_object()
            if instance.customer != user.customer_profile:
                return Response(
                    {"detail": "You do not have permission to modify this order."},
                    status=status.HTTP_403_FORBIDDEN
                )

            import datetime
            from rest_framework.exceptions import ValidationError
            from routing.models import Route, RouteStatus
            
            date_str = request.data.get("scheduled_delivery_date") or str(instance.scheduled_delivery_date)
            if date_str:
                try:
                    if isinstance(date_str, str):
                        delivery_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                    else:
                        delivery_date = date_str
                except ValueError:
                    delivery_date = None
                
                if delivery_date == datetime.date.today():
                    active_routes = Route.objects.filter(
                        delivery_date=delivery_date,
                        orders__customer=user.customer_profile,
                        status__in=[RouteStatus.IN_PROGRESS, RouteStatus.COMPLETED]
                    )
                    if active_routes.exists():
                        raise ValidationError(
                            "Cannot update order for today: Your delivery route for today has already departed (in transit/completed)."
                        )

            if hasattr(request.data, "_mutable"):
                request.data._mutable = True
            request.data["customer"] = user.customer_profile.id
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        user = request.user
        is_customer = hasattr(user, "customer_profile") and user.customer_profile is not None
        if is_customer:
            instance = self.get_object()
            if instance.customer != user.customer_profile:
                return Response(
                    {"detail": "You do not have permission to delete this order."},
                    status=status.HTTP_403_FORBIDDEN
                )
            if instance.status not in [OrderStatus.PENDING, OrderStatus.CONFIRMED]:
                return Response(
                    {"detail": "You cannot delete an order that has already been dispatched or delivered."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=["post"], url_path="sync")
    def sync(self, request):
        """
        Master sync endpoint that:
        1. Auto-assigns zones to customers based on spatial location.
        2. Re-assigns pending/confirmed orders to zone drivers (creates optimized routes).
        3. Returns the refreshed, serialized order list.
        """
        import datetime as dt
        from routing.models import Zone
        from crm.models import Customer, HAS_GIS, _parse_coordinates, _point_in_polygon
        from orders.services import create_optimized_route

        # ---------- STEP 1: Auto-assign zones to customers ----------
        customers = Customer.objects.filter(is_active=True).exclude(location=None)
        zones_qs = Zone.objects.filter(is_active=True)
        zones_list = list(zones_qs)

        zone_updated = 0
        for customer in customers:
            loc = customer.location
            if not loc:
                continue

            assigned_zone = None
            if HAS_GIS:
                from django.contrib.gis.geos import Point

                if not isinstance(loc, Point):
                    coords = _parse_coordinates(loc)
                    if coords:
                        loc = Point(coords[0], coords[1])
                    else:
                        continue
                assigned_zone = Zone.objects.filter(
                    boundary__contains=loc, is_active=True
                ).first()
            else:
                coords = _parse_coordinates(loc)
                if coords:
                    lng, lat = coords
                    for zone in zones_list:
                        if zone.boundary:
                            poly_coords = None
                            if isinstance(zone.boundary, dict):
                                geom_type = zone.boundary.get("type")
                                if geom_type == "Polygon":
                                    poly_coords = zone.boundary.get("coordinates")
                                elif geom_type == "MultiPolygon":
                                    for sub_poly in zone.boundary.get(
                                        "coordinates", []
                                    ):
                                        if _point_in_polygon(lng, lat, sub_poly):
                                            assigned_zone = zone
                                            break
                            if assigned_zone:
                                break
                            if poly_coords and _point_in_polygon(lng, lat, poly_coords):
                                assigned_zone = zone
                                break

            if assigned_zone and customer.zone != assigned_zone:
                customer.zone = assigned_zone
                customer.save(update_fields=["zone"])
                zone_updated += 1

        # ---------- STEP 2: Re-assign pending orders to zone drivers ----------
        date_str = request.data.get("date") or dt.date.today().isoformat()

        pending_orders = Order.objects.filter(
            scheduled_delivery_date=date_str,
            status__in=[OrderStatus.PENDING, OrderStatus.CONFIRMED],
            customer__zone__isnull=False,
        ).exclude(
            customer__is_new=True,
            customer__trial_approved=False
        ).select_related("customer__zone", "customer__zone__assigned_driver")

        # Group orders by zone
        zone_orders = {}
        for order in pending_orders:
            zone = order.customer.zone
            if zone:
                zone_orders.setdefault(zone, []).append(order)

        routes_created = 0
        route_errors = []
        from routing.models import Driver

        for zone, z_orders in zone_orders.items():
            driver_user = zone.assigned_driver
            if not driver_user:
                route_errors.append(
                    {"zone": zone.name, "error": "No primary driver assigned."}
                )
                continue

            # Safely convert User to Driver profile
            driver_profile = getattr(driver_user, "driver_profile", None)
            if not driver_profile:
                driver_profile = Driver.objects.filter(user=driver_user).first()

            if not driver_profile:
                route_errors.append(
                    {
                        "zone": zone.name,
                        "error": f"Primary driver '{driver_user.username}' has no Driver profile.",
                    }
                )
                continue

            # Resolve warehouse and warehouse_location coordinates for pathfinder
            warehouse = driver_profile.warehouse
            warehouse_location = None
            if (
                warehouse
                and warehouse.latitude is not None
                and warehouse.longitude is not None
            ):
                warehouse_location = {
                    "longitude": float(warehouse.longitude),
                    "latitude": float(warehouse.latitude),
                }

            order_ids = [str(o.id) for o in z_orders]
            route_name = f"{zone.name} - {date_str}"

            try:
                create_optimized_route(
                    route_name,
                    driver_profile,
                    date_str,
                    order_ids,
                    warehouse=warehouse,
                    warehouse_location=warehouse_location,
                )
                routes_created += 1
            except Exception as e:
                route_errors.append({"zone": zone.name, "error": str(e)})

        # ---------- STEP 3: Return refreshed order list ----------
        qs = self.get_queryset()
        serializer = self.get_serializer(qs, many=True)

        return Response(
            {
                "orders": serializer.data,
                "sync_summary": {
                    "customers_zone_updated": zone_updated,
                    "routes_created": routes_created,
                    "route_errors": route_errors,
                },
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["patch", "put"])
    def bulk_update(self, request):
        """
        Updates multiple orders at once. Each must have an 'id'.
        """
        data = request.data
        if not isinstance(data, list):
            return Response(
                {"detail": "Expected a list."}, status=status.HTTP_400_BAD_REQUEST
            )

        updated = []
        for item in data:
            order_id = item.get("id")
            if not order_id:
                continue
            try:
                instance = Order.objects.get(id=order_id)
                serializer = self.get_serializer(instance, data=item, partial=True)
                serializer.is_valid(raise_exception=True)
                serializer.save()
                updated.append(serializer.data)
            except Order.DoesNotExist:
                continue
        return Response(updated, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="special")
    def special_orders(self, request):
        """Returns all special/extra orders (non-subscription orders)."""
        qs = self.get_queryset().filter(is_special=True)
        # Additional filters from query params
        customer_id = request.query_params.get("customer")
        if customer_id:
            qs = qs.filter(customer_id=customer_id)
        date = request.query_params.get("scheduled_delivery_date")
        if date:
            qs = qs.filter(scheduled_delivery_date=date)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="mark-delivered")
    def mark_delivered(self, request, pk=None):
        order = self.get_object()
        bottles_returned = int(request.data.get("bottles_returned", 0))
        bottles_issued = request.data.get("bottles_issued")
        if bottles_issued is not None:
            try:
                bottles_issued = int(bottles_issued)
            except (ValueError, TypeError):
                bottles_issued = None

        pod_image = request.FILES.get("pod_image")
        pod_lat = request.data.get("pod_latitude")
        pod_lon = request.data.get("pod_longitude")

        payment_method = request.data.get("payment_method")
        amount_collected = request.data.get("amount_collected")
        payment_transaction_id = request.data.get("payment_transaction_id", "")

        from orders.models import PaymentMethod, PaymentStatus

        # Validate payment_method
        if payment_method not in PaymentMethod.values:
            payment_method = PaymentMethod.ON_ACCOUNT

        if amount_collected is not None:
            try:
                amount_collected = float(amount_collected)
            except (ValueError, TypeError):
                amount_collected = 0.0
        else:
            amount_collected = 0.0

        payment_status = PaymentStatus.PENDING
        if payment_method in [PaymentMethod.CASH, PaymentMethod.UPI] and amount_collected > 0:
            payment_status = PaymentStatus.PAID

        # Check if POD is required for this tenant
        from administration.models import AdminConfiguration

        config = AdminConfiguration.get_solo()
        if config.enable_delivery_photo and not pod_image:
            return Response(
                {
                    "detail": "Proof of Delivery (photo) is required by your administrator."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        from django.db import transaction
        from django.utils import timezone

        bottle_transactions_data = request.data.get("bottle_transactions")
        with transaction.atomic():
            order.status = OrderStatus.DELIVERED
            order.delivered_at = timezone.now()
            if pod_image:
                order.pod_image = pod_image
            if pod_lat:
                order.pod_latitude = pod_lat
            if pod_lon:
                order.pod_longitude = pod_lon

            order.payment_method = payment_method
            order.amount_collected = amount_collected
            order.payment_transaction_id = payment_transaction_id
            order.payment_status = payment_status

            order.save(
                update_fields=[
                    "status",
                    "delivered_at",
                    "pod_image",
                    "pod_latitude",
                    "pod_longitude",
                    "payment_method",
                    "amount_collected",
                    "payment_transaction_id",
                    "payment_status",
                ]
            )

            from inventory.services import record_bottle_transaction
            from inventory.models import BottleTransactionType, BottleType

            user_recorded = request.user if not request.user.is_anonymous else None

            if bottle_transactions_data is not None and isinstance(
                bottle_transactions_data, list
            ):
                for txn_data in bottle_transactions_data:
                    bt_id = txn_data.get("bottle_type_id")
                    if not bt_id:
                        continue
                    try:
                        bottle_type = BottleType.objects.get(id=bt_id)
                    except BottleType.DoesNotExist:
                        continue

                    issued_qty = int(txn_data.get("issued", 0))
                    returned_qty = int(txn_data.get("returned", 0))
                    broken_qty = int(txn_data.get("broken", 0))

                    if issued_qty > 0:
                        record_bottle_transaction(
                            bottle_type=bottle_type,
                            quantity=issued_qty,
                            transaction_type=BottleTransactionType.ISSUED,
                            customer=order.customer,
                            order=order,
                            user=user_recorded,
                        )
                    if returned_qty > 0:
                        record_bottle_transaction(
                            bottle_type=bottle_type,
                            quantity=returned_qty,
                            transaction_type=BottleTransactionType.RETURNED,
                            customer=order.customer,
                            order=order,
                            user=user_recorded,
                        )
                    if broken_qty > 0:
                        record_bottle_transaction(
                            bottle_type=bottle_type,
                            quantity=broken_qty,
                            transaction_type=BottleTransactionType.BROKEN,
                            customer=order.customer,
                            order=order,
                            user=user_recorded,
                        )
            else:
                for item in order.items.all():
                    if item.product.is_returnable and item.product.bottle_type:
                        qty = (
                            bottles_issued
                            if bottles_issued is not None
                            else item.quantity
                        )
                        record_bottle_transaction(
                            bottle_type=item.product.bottle_type,
                            quantity=qty,
                            transaction_type=BottleTransactionType.ISSUED,
                            customer=order.customer,
                            order=order,
                            user=user_recorded,
                        )

                if bottles_returned > 0:
                    first_item = order.items.filter(product__is_returnable=True).first()
                    if first_item:
                        record_bottle_transaction(
                            bottle_type=first_item.product.bottle_type,
                            quantity=bottles_returned,
                            transaction_type=BottleTransactionType.RETURNED,
                            customer=order.customer,
                            order=order,
                            user=user_recorded,
                        )

        # Send push notification to the customer
        try:
            from notifications.services import send_push_notification
            if order.customer and order.customer.user:
                title = "🎉 Order Delivered!"
                body = "Woohoo! Your order has been delivered fresh to your doorstep. Enjoy! 🥛✨"
                send_push_notification(
                    user=order.customer.user,
                    title=title,
                    body=body,
                    order=order,
                    notification_type='order_status'
                )
        except Exception as e:
            print(f"[Delivery Push Notification Error] {e}")

        # Send push notification to the driver
        try:
            from notifications.services import send_push_notification
            if hasattr(order, 'route_stop') and order.route_stop and order.route_stop.route:
                driver_user = order.route_stop.route.driver
                if driver_user:
                    title = "📦 Delivery Confirmed!"
                    customer_name = order.customer.name if order.customer else "Customer"
                    body = f"Great work! Order delivered successfully to {customer_name}. 🌟"
                    send_push_notification(
                        user=driver_user,
                        title=title,
                        body=body,
                        order=order,
                        notification_type='order_status'
                    )
        except Exception as e:
            print(f"[Driver Delivery Push Notification Error] {e}")

        # Broadcast real-time delivery notification to admins
        try:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer

            channel_layer = get_channel_layer()
            if channel_layer:
                driver_name = request.user.get_full_name() or request.user.username
                customer_name = order.customer.name
                async_to_sync(channel_layer.group_send)(
                    "admins",
                    {
                        "type": "broadcast_location",
                        "notification_type": "order_delivered",
                        "title": "Order Delivered! 📦🎉",
                        "message": f"Driver '{driver_name}' has successfully delivered Order #{order.id} to {customer_name}.",
                        "order_id": str(order.id),
                        "customer_name": customer_name,
                        "driver_name": driver_name,
                        "timestamp": timezone.now().isoformat(),
                    },
                )
        except Exception as e:
            print(f"[Delivery WS Broadcast Error] {e}")

        return Response(OrderSerializer(order).data)

    @action(detail=True, methods=["post"], url_path="mark-undelivered")
    def mark_undelivered(self, request, pk=None):
        order = self.get_object()
        pod_image = request.FILES.get("pod_image")
        pod_lat = request.data.get("pod_latitude")
        pod_lon = request.data.get("pod_longitude")

        if not pod_image:
            return Response(
                {
                    "detail": "Proof of Attempt (photo) is required to mark an order as undelivered."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        from django.db import transaction
        from django.utils import timezone

        with transaction.atomic():
            order.status = OrderStatus.UNDELIVERED
            order.delivered_at = timezone.now()
            order.pod_image = pod_image
            if pod_lat:
                order.pod_latitude = pod_lat
            if pod_lon:
                order.pod_longitude = pod_lon
            order.save(
                update_fields=[
                    "status",
                    "delivered_at",
                    "pod_image",
                    "pod_latitude",
                    "pod_longitude",
                ]
            )

        # Send push notification to the customer
        try:
            from notifications.services import send_push_notification
            if order.customer and order.customer.user:
                title = "⚠️ Delivery Attempt Failed"
                body = "We missed you today! We couldn't deliver your order, but we'll try again on our next run. 🚚"
                send_push_notification(
                    user=order.customer.user,
                    title=title,
                    body=body,
                    order=order,
                    notification_type='order_status'
                )
        except Exception as e:
            print(f"[Delivery Attempt Failed Push Notification Error] {e}")

        return Response(OrderSerializer(order).data)

    @action(detail=False, methods=["post"], url_path="mark-all-delivered")
    def mark_all_delivered(self, request):
        route_id = request.data.get("route_id")
        delivery_date = (
            request.data.get("delivery_date")
            or request.data.get("date")
            or request.data.get("scheduled_delivery_date")
        )

        if not route_id and not delivery_date:
            return Response(
                {
                    "error": "Please provide either route_id or delivery_date/date to scope the mass update."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        orders = Order.objects.exclude(
            status__in=[
                OrderStatus.DELIVERED,
                OrderStatus.CANCELLED,
                OrderStatus.UNDELIVERED,
            ]
        )

        if route_id:
            orders = orders.filter(route_stop__route_id=route_id)
        if delivery_date:
            orders = orders.filter(scheduled_delivery_date=delivery_date)

        from django.utils import timezone

        # Load the orders to send notifications
        orders_to_notify = list(orders.select_related("customer__user"))

        count = 0
        from django.db import transaction
        with transaction.atomic():
            for order in orders_to_notify:
                order.status = OrderStatus.DELIVERED
                order.delivered_at = timezone.now()
                order.save(update_fields=["status", "delivered_at"])
                count += 1

                # Send push notification
                try:
                    from notifications.services import send_push_notification
                    if order.customer and order.customer.user:
                        title = "🎉 Order Delivered!"
                        body = "Woohoo! Your order has been delivered fresh to your doorstep. Enjoy! 🥛✨"
                        send_push_notification(
                            user=order.customer.user,
                            title=title,
                            body=body,
                            order=order,
                            notification_type='order_status'
                        )
                except Exception as e:
                    print(f"[Delivery Push Notification Error] {e}")

        return Response({"detail": f"Marked {count} orders as delivered."})


class RouteViewSet(viewsets.ModelViewSet):
    serializer_class = RouteSerializer
    permission_classes = [IsERPUser, HasGroupPermission]
    required_groups = ["Logistics_Managers", "ERP_Admins"]
    filterset_fields = ["delivery_date", "is_completed"]

    def update(self, request, *args, **kwargs):
        is_completed = request.data.get("is_completed")
        status_val = request.data.get("status")
        if (
            is_completed is True
            or str(is_completed).lower() == "true"
            or status_val == "completed"
        ):
            return Response(
                {"error": "Manual trip completion is disabled. Trips are automatically completed by the system at 12:00 PM."},
                status=400
            )
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        is_completed = request.data.get("is_completed")
        status_val = request.data.get("status")
        if (
            is_completed is True
            or str(is_completed).lower() == "true"
            or status_val == "completed"
        ):
            return Response(
                {"error": "Manual trip completion is disabled. Trips are automatically completed by the system at 12:00 PM."},
                status=400
            )
        return super().partial_update(request, *args, **kwargs)

    def get_queryset(self):
        from django.db.models import Count

        queryset = (
            Route.objects.annotate(stops_count=Count("stops"))
            .filter(stops_count__gt=0)
            .select_related("driver")
            .prefetch_related(
                "stops__order__customer__zone",
                "stops__order__items__product__bottle_type",
                "stops__order__subscription__items__product",
                "stops__order__customer__subscriptions__items__product",
                "additional_drivers"
            )
        )
        driver_id = self.request.query_params.get("driver")
        if driver_id:
            from django.db.models import Q

            queryset = queryset.filter(
                Q(driver_id=driver_id) | Q(additional_drivers__id=driver_id)
            ).distinct()
        return queryset

    @action(detail=False, methods=["post"], url_path="create-optimized")
    def create_optimized(self, request):
        name = request.data.get("name")
        # Support both 'date' and 'delivery_date'
        date = request.data.get("date") or request.data.get("delivery_date")
        order_ids = request.data.get("order_ids", [])
        driver_id = request.data.get("driver_id")
        zone_id = request.data.get("zone")

        # If a zone is provided, resolve order_ids, name, and driver automatically
        if zone_id:
            from routing.models import Zone

            zone = Zone.objects.filter(id=zone_id).first()
            if not zone:
                return Response(
                    {"detail": f"Zone with ID {zone_id} not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Fetch all pending or confirmed orders for this zone and date
            orders = Order.objects.filter(
                customer__zone_id=zone_id,
                scheduled_delivery_date=date,
                status__in=[OrderStatus.PENDING, OrderStatus.CONFIRMED],
            )

            if not orders.exists():
                return Response(
                    {
                        "detail": f"No pending or confirmed orders found in zone '{zone.name}' for date {date}."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if not name:
                route_count = Route.objects.filter(delivery_date=date).count()
                name = f"{zone.name} - {date} #{route_count + 1}"
            if not driver_id and zone.assigned_driver:
                driver_id = zone.assigned_driver.id

        # Validation with descriptive errors
        missing_fields = []
        if not name:
            missing_fields.append("name")
        if not date:
            missing_fields.append("date/delivery_date")
        if not order_ids:
            missing_fields.append("order_ids")

        if missing_fields:
            return Response(
                {
                    "detail": f"Missing required fields: {', '.join(missing_fields)}",
                    "received_data": request.data,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        from accounts.models import User
        from routing.models import Driver

        driver_user = User.objects.filter(id=driver_id).first() if driver_id else None

        driver_profile = None
        warehouse = None
        warehouse_location = None
        if driver_user:
            driver_profile = getattr(driver_user, "driver_profile", None)
            if not driver_profile:
                driver_profile = Driver.objects.filter(user=driver_user).first()

            if driver_profile:
                warehouse = driver_profile.warehouse
                if (
                    warehouse
                    and warehouse.latitude is not None
                    and warehouse.longitude is not None
                ):
                    warehouse_location = {
                        "longitude": float(warehouse.longitude),
                        "latitude": float(warehouse.latitude),
                    }

        if name and "#" not in name:
            route_count = Route.objects.filter(delivery_date=date).count()
            name = f"{name} #{route_count + 1}"

        route = create_optimized_route(
            name,
            driver_profile or driver_user,
            date,
            order_ids,
            warehouse=warehouse,
            warehouse_location=warehouse_location,
        )

        # Return the route with extra debug info to help troubleshoot empty stops
        response_data = RouteSerializer(route).data
        response_data["debug"] = {
            "requested_order_ids_count": len(order_ids),
            "orders_found_in_db": Order.objects.filter(id__in=order_ids).count(),
            "valid_orders_with_locations": Order.objects.filter(id__in=order_ids)
            .exclude(customer__location__isnull=True)
            .count(),
        }
        return Response(response_data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="assign-pending")
    def assign_pending(self, request):
        """
        Bulk-assigns pending orders of customers to their primary zone drivers and creates optimized routes.
        """
        date = request.data.get("date") or request.data.get("delivery_date")
        if not date:
            import datetime

            date = datetime.date.today().isoformat()

        from routing.models import Zone
        from orders.services import create_optimized_route

        # Fetch pending or confirmed orders for this date that are in a zone
        orders = Order.objects.filter(
            scheduled_delivery_date=date,
            status__in=[OrderStatus.PENDING, OrderStatus.CONFIRMED],
            customer__zone__isnull=False,
        ).select_related("customer__zone", "customer__zone__assigned_driver")

        # Group by zone
        zone_orders = {}
        for order in orders:
            zone = order.customer.zone
            if zone:
                zone_orders.setdefault(zone, []).append(order)

        created_routes = []
        errors = []

        from routing.models import Driver

        for zone, z_orders in zone_orders.items():
            driver_user = zone.assigned_driver
            if not driver_user:
                errors.append(
                    {
                        "zone_id": str(zone.id),
                        "zone_name": zone.name,
                        "error": "No primary driver assigned to this zone.",
                    }
                )
                continue

            # Safely convert User to Driver profile
            driver_profile = getattr(driver_user, "driver_profile", None)
            if not driver_profile:
                driver_profile = Driver.objects.filter(user=driver_user).first()

            if not driver_profile:
                errors.append(
                    {
                        "zone_id": str(zone.id),
                        "zone_name": zone.name,
                        "error": f"Primary driver '{driver_user.username}' has no Driver profile.",
                    }
                )
                continue

            # Resolve warehouse and warehouse_location coordinates for pathfinder
            warehouse = driver_profile.warehouse
            warehouse_location = None
            if (
                warehouse
                and warehouse.latitude is not None
                and warehouse.longitude is not None
            ):
                warehouse_location = {
                    "longitude": float(warehouse.longitude),
                    "latitude": float(warehouse.latitude),
                }

            order_ids = [str(o.id) for o in z_orders]
            route_count = Route.objects.filter(delivery_date=date).count()
            name = f"{zone.name} - {date} #{route_count + 1}"

            try:
                route = create_optimized_route(
                    name,
                    driver_profile,
                    date,
                    order_ids,
                    warehouse=warehouse,
                    warehouse_location=warehouse_location,
                )
                created_routes.append(RouteSerializer(route).data)
            except Exception as e:
                errors.append(
                    {"zone_id": str(zone.id), "zone_name": zone.name, "error": str(e)}
                )

        return Response(
            {
                "date": date,
                "total_zones_processed": len(zone_orders),
                "created_routes": created_routes,
                "errors": errors,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="trigger-daily-generation")
    def trigger_daily_generation(self, request):
        """
        Manually trigger the full daily route generation process for a specific date.
        Generates orders from subscriptions and builds optimized routes.
        """
        date_str = request.data.get("date")
        if not date_str:
            return Response({"detail": "Missing target 'date' in payload (format: YYYY-MM-DD)."}, status=400)
        
        try:
            import datetime
            target_date = datetime.date.fromisoformat(date_str)
        except ValueError:
            return Response({"detail": "Invalid date format. Use YYYY-MM-DD."}, status=400)

        from orders.services.route_generator import generate_daily_routes_for_date
        
        # Run generation
        try:
            summary = generate_daily_routes_for_date(target_date)
        except Exception as e:
            import traceback
            print("================================== EXCEPTION IN TRIGGER_DAILY_GENERATION ==================================")
            traceback.print_exc()
            print("==========================================================================================================")
            raise e
        return Response({
            "message": f"Daily route generation completed for {date_str}.",
            "summary": summary
        })

    @action(detail=False, methods=["post"], url_path="clear-daily-generation")
    def clear_daily_generation(self, request):
        """
        Manually clear/reverse the route generation for a specific date.
        Deletes all routes, route stops, and orders created for that date.
        """
        date_str = request.data.get("date")
        if not date_str:
            return Response({"detail": "Missing target 'date' in payload (format: YYYY-MM-DD)."}, status=400)
            
        try:
            import datetime
            target_date = datetime.date.fromisoformat(date_str)
        except ValueError:
            return Response({"detail": "Invalid date format. Use YYYY-MM-DD."}, status=400)

        from orders.models import Route, Order, RouteStop
        from django.db import transaction

        with transaction.atomic():
            # Find routes for that date
            routes = Route.objects.filter(delivery_date=target_date)
            routes_count = routes.count()
            
            # Delete route stops associated with these routes
            stops_count = RouteStop.objects.filter(route__delivery_date=target_date).delete()[0]
            
            # Delete routes
            routes.delete()
            
            # Delete orders created automatically from subscriptions for this date
            # We identify them by having a subscription reference
            orders_deleted = Order.objects.filter(
                scheduled_delivery_date=target_date,
                subscription__isnull=False
            ).delete()[0]

        return Response({
            "message": f"Successfully reversed/cleared daily generation for {date_str}.",
            "details": {
                "deleted_routes": routes_count,
                "deleted_route_stops": stops_count,
                "deleted_subscription_orders": orders_deleted
            }
        })

    @action(detail=False, methods=["get"], url_path="control-panel", permission_classes=[])
    def control_panel(self, request):
        """
        Render the manual testing control panel page.
        """
        import os
        from django.conf import settings
        from django.http import HttpResponse

        template_path = os.path.join(settings.BASE_DIR, "templates", "control_panel.html")
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                html_content = f.read()
            return HttpResponse(html_content, content_type="text/html")
        except Exception as e:
            return HttpResponse(f"Error loading control panel: {e}", status=500)

    @action(detail=True, methods=["get"], url_path="geojson")
    def geojson(self, request, pk=None):
        route = self.get_object()
        features = []

        if route.geometry:
            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[p[0], p[1]] for p in route.geometry.coords],
                    },
                    "properties": {
                        "type": "route_path",
                        "name": route.name,
                        "distance_km": float(route.total_distance_km),
                    },
                }
            )

        for stop in route.stops.all():
            loc = stop.order.customer.location
            if loc:
                features.append(
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [loc.x, loc.y]},
                        "properties": {
                            "type": "stop",
                            "sequence": stop.sequence_number,
                            "customer": stop.order.customer.name,
                            "address": stop.order.delivery_address,
                            "order_id": str(stop.order.id),
                            "status": stop.order.status,
                        },
                    }
                )

        return Response({"type": "FeatureCollection", "features": features})

    @action(detail=False, methods=["post"], url_path="generate")
    def generate_routes(self, request):
        """
        Manually triggers next day's automatic route/trip generation.
        """
        date_str = request.data.get("date")
        if date_str:
            try:
                target_date = datetime.date.fromisoformat(date_str)
            except ValueError:
                return Response(
                    {"detail": "Invalid date format. Expected YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            target_date = datetime.date.today() + datetime.timedelta(days=1)

        results = generate_daily_routes_for_date(target_date)
        return Response(results, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="regenerate")
    def regenerate_routes(self, request):
        """
        Manually triggers daily route regeneration (deletes old incomplete routes and regenerates).
        """
        date_str = request.data.get("date")
        if date_str:
            try:
                target_date = datetime.date.fromisoformat(date_str)
            except ValueError:
                return Response(
                    {"detail": "Invalid date format. Expected YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            target_date = datetime.date.today() + datetime.timedelta(days=1)

        results = regenerate_daily_routes_for_date(target_date)
        return Response(results, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="lock")
    def lock_route(self, request, pk=None):
        """
        Locks the route to prevent any order changes.
        """
        success = lock_route_for_trip(pk)
        if success:
            return Response(
                {"status": "locked", "detail": "Route locked successfully."},
                status=status.HTTP_200_OK,
            )
        return Response(
            {"error": "Failed to lock route or route not found."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    @action(detail=True, methods=["post"], url_path="unlock")
    def unlock_route(self, request, pk=None):
        """
        Unlocks the route to enable order changes.
        """
        success = unlock_route_for_trip(pk)
        if success:
            return Response(
                {"status": "unlocked", "detail": "Route unlocked successfully."},
                status=status.HTTP_200_OK,
            )
        return Response(
            {"error": "Failed to unlock route or route not found."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    @action(detail=False, methods=["post"], url_path="refresh-and-merge")
    def refresh_and_merge(self, request):
        """
        Refreshes and merges duplicate routes for a single driver,
        and assigns any unassigned pending/confirmed orders to the next available active route.
        """
        import datetime
        from django.db import transaction
        from orders.models import Order, OrderStatus, Route, RouteStop
        from orders.services import create_optimized_route
        from routing.models import Driver

        # 1. Resolve date
        date_str = request.data.get("date") or request.data.get("delivery_date")
        if date_str:
            try:
                target_date = datetime.date.fromisoformat(date_str)
            except ValueError:
                try:
                    target_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                except ValueError:
                    return Response(
                        {"detail": "Invalid date format. Expected YYYY-MM-DD."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
        else:
            target_date = datetime.date.today()

        routes_merged = 0
        orders_assigned = 0

        with transaction.atomic():
            # 2. Find and merge duplicate routes for each driver
            all_routes = Route.objects.filter(
                delivery_date=target_date
            ).prefetch_related("stops__order")

            # Group active routes by driver User ID
            driver_routes = {}
            for r in all_routes:
                if r.driver_id:
                    driver_routes.setdefault(r.driver_id, []).append(r)

            for driver_id, routes in driver_routes.items():
                if len(routes) > 1:
                    # Collect all stops/orders across all routes for this driver
                    all_order_ids = set()
                    for r in routes:
                        for stop in r.stops.all():
                            all_order_ids.add(str(stop.order_id))
                            # If the order was marked undelivered (e.g. by auto-closing), reset it to pending
                            if stop.order.status == OrderStatus.UNDELIVERED:
                                stop.order.status = OrderStatus.PENDING
                                stop.order.delivered_at = None
                                stop.order.save(update_fields=["status", "delivered_at"])

                    # Pick the best primary route to survive:
                    # Prefer the one that is not completed and/or is started
                    routes.sort(key=lambda r: (r.is_completed, r.started_at is None))
                    primary_route = routes[0]
                    
                    # If the primary route was completed, reactivate it
                    if primary_route.is_completed:
                        primary_route.is_completed = False
                        primary_route.status = RouteStatus.PENDING
                        primary_route.save(update_fields=["is_completed", "status"])

                    # Delete extra duplicate routes
                    for extra_route in routes[1:]:
                        extra_route.stops.all().delete()
                        extra_route.delete()
                        routes_merged += 1

                    # Resolve warehouse & warehouse_location for primary driver
                    warehouse = None
                    warehouse_location = None
                    driver_profile = Driver.objects.filter(user_id=driver_id).first()
                    if driver_profile:
                        warehouse = driver_profile.warehouse
                        if warehouse and warehouse.latitude is not None and warehouse.longitude is not None:
                            warehouse_location = {
                                "longitude": float(warehouse.longitude),
                                "latitude": float(warehouse.latitude),
                            }

                    # Re-optimize/recreate stops on primary_route in-place
                    create_optimized_route(
                        primary_route.name,
                        primary_route.driver,
                        target_date,
                        list(all_order_ids),
                        warehouse=warehouse,
                        warehouse_location=warehouse_location,
                    )

            # 3. Find pending/confirmed orders for this date that are not on any route
            unassigned_orders = Order.objects.filter(
                scheduled_delivery_date=target_date,
                status__in=[OrderStatus.PENDING, OrderStatus.CONFIRMED],
                route_stop__isnull=True,
            ).select_related("customer__zone", "customer__zone__assigned_driver")

            # Resolve all driver profiles to match warehouses
            driver_profiles = {
                dp.user_id: dp for dp in Driver.objects.select_related("warehouse").all()
            }

            for order in unassigned_orders:
                customer = order.customer
                zone = customer.zone if customer else None
                assigned_driver = zone.assigned_driver if zone else None

                target_route = None

                # Option A: Check if the assigned driver already has a route
                if assigned_driver:
                    target_route = Route.objects.filter(
                        driver=assigned_driver,
                        delivery_date=target_date,
                        is_completed=False,
                    ).first()

                # Option B: Fallback to next available active route for the zone's driver's warehouse
                if not target_route and zone:
                    driver_profile = driver_profiles.get(assigned_driver.id) if assigned_driver else None
                    warehouse = driver_profile.warehouse if driver_profile else None
                    if warehouse:
                        # Find any active route on that date associated with that warehouse
                        target_route = Route.objects.filter(
                            delivery_date=target_date,
                            is_completed=False,
                            driver__driver_profile__warehouse=warehouse,
                        ).first()

                # Option C: Fallback to any active incomplete route on that date
                if not target_route:
                    target_route = Route.objects.filter(
                        delivery_date=target_date,
                        is_completed=False,
                    ).first()

                # Option D: If no route exists at all, but we have a driver assigned to the zone, create a new route
                if not target_route and assigned_driver:
                    driver_profile = driver_profiles.get(assigned_driver.id)
                    warehouse = driver_profile.warehouse if driver_profile else None
                    warehouse_location = None
                    if warehouse and warehouse.latitude is not None and warehouse.longitude is not None:
                        warehouse_location = {
                            "longitude": float(warehouse.longitude),
                            "latitude": float(warehouse.latitude),
                        }
                    
                    route_count = Route.objects.filter(delivery_date=target_date).count()
                    route_name = f"{zone.name} - {assigned_driver.get_full_name() or assigned_driver.username} - {target_date.strftime('%Y-%m-%d')} #{route_count + 1}"
                    
                    target_route = create_optimized_route(
                        route_name,
                        assigned_driver,
                        target_date,
                        [str(order.id)],
                        warehouse=warehouse,
                        warehouse_location=warehouse_location,
                    )
                    orders_assigned += 1
                    continue

                # If we found a target route, add the order to it and re-optimize
                if target_route:
                    # Get existing orders on that route
                    existing_order_ids = list(target_route.stops.values_list("order_id", flat=True))
                    merged_order_ids = list(set(str(oid) for oid in existing_order_ids) | {str(order.id)})

                    driver_profile = driver_profiles.get(target_route.driver_id)
                    warehouse = driver_profile.warehouse if driver_profile else None
                    warehouse_location = None
                    if warehouse and warehouse.latitude is not None and warehouse.longitude is not None:
                        warehouse_location = {
                            "longitude": float(warehouse.longitude),
                            "latitude": float(warehouse.latitude),
                        }

                    create_optimized_route(
                        target_route.name,
                        target_route.driver,
                        target_date,
                        merged_order_ids,
                        warehouse=warehouse,
                        warehouse_location=warehouse_location,
                    )
                    orders_assigned += 1

        return Response(
            {
                "status": "success",
                "date": str(target_date),
                "routes_merged": routes_merged,
                "orders_assigned": orders_assigned,
            },
            status=status.HTTP_200_OK,
        )


class DriverViewSet(viewsets.ViewSet):
    """
    Dedicated endpoints for the Driver Mobile App.
    """

    permission_classes = [IsAuthenticated, HasGroupPermission]
    required_groups = ["Drivers", "Logistics_Managers"]

    def retrieve(self, request, pk=None):
        return Response({"detail": "Use specific actions like start-trip"})

    @action(detail=False, methods=["get"], url_path="trip-status")
    def trip_status(self, request):
        """
        Checks if the logged-in driver's trip is started or not.
        Returns the on_trip status and information about the active route.
        """
        from django_tenants.utils import schema_context
        from django.db import connection

        user = request.user
        schema = user.tenant_schema
        context_schema = (
            schema
            if connection.schema_name == "public" and schema
            else connection.schema_name
        )

        with schema_context(context_schema):
            from routing.models import Driver
            import datetime as _dt

            driver_profile = Driver.objects.filter(user=user).first()

            # Find the active route for this driver
            # Priority: today's incomplete route first, then any other incomplete route
            from django.db.models import Q, Count

            today = _dt.date.today()

            # 1. First look for today's incomplete route (only if it has stops)
            active_route = (
                Route.objects.annotate(stops_count=Count("stops"))
                .filter(
                    Q(driver=user) | Q(additional_drivers=user),
                    is_completed=False,
                    delivery_date=today,
                    stops_count__gt=0,
                )
                .distinct()
                .order_by("-created_at")
                .first()
            )

            # 2. Fallback: find any incomplete route (for routes without a date or future routes, with stops)
            if not active_route:
                active_route = (
                    Route.objects.annotate(stops_count=Count("stops"))
                    .filter(
                        Q(driver=user) | Q(additional_drivers=user),
                        is_completed=False,
                        stops_count__gt=0,
                    )
                    .distinct()
                    .order_by("-delivery_date")
                    .first()
                )
            on_trip = False
            route_data = None
            if active_route:
                is_started = (
                    active_route.started_at is not None and 
                    not active_route.is_completed and 
                    active_route.status not in ['completed', 'stopped']
                )
                route_data = {
                    "id": str(active_route.id),
                    "route_id": str(active_route.id),
                    "name": active_route.name,
                    "delivery_date": active_route.delivery_date,
                    "started_at": active_route.started_at,
                    "is_started": active_route.started_at is not None,
                }
                # Only consider the trip as started if the route has actually been started and is not completed/stopped
                if is_started:
                    on_trip = True

            # Sync the DB flag if it drifted out of sync
            if driver_profile and driver_profile.on_trip != on_trip:
                driver_profile.on_trip = on_trip
                driver_profile.save(update_fields=["on_trip"])

            return Response({"on_trip": on_trip, "active_route": route_data})

    @action(detail=False, methods=["get"], url_path="my-route")
    def my_route(self, request):
        """
        Returns the active route for the logged-in driver for today.
        """
        from django_tenants.utils import schema_context
        from django.db import connection

        user = request.user
        schema = user.tenant_schema

        # If we are in public schema, switch to driver's schema
        context_schema = (
            schema
            if connection.schema_name == "public" and schema
            else connection.schema_name
        )
        with schema_context(context_schema):
            # Look for the oldest incomplete active route (only if it has stops)
            from django.db.models import Q, Count

            route = (
                Route.objects.annotate(stops_count=Count("stops"))
                .filter(
                    Q(driver=user) | Q(additional_drivers=user),
                    is_completed=False,
                    stops_count__gt=0,
                )
                .distinct()
                .prefetch_related("stops__order__customer")
                .order_by("delivery_date")
                .first()
            )

            if not route:
                return Response(
                    {"detail": "No active route found for today."}, status=404
                )

            from orders.models import RouteStatus, OrderStatus

            # If the route is not locked and not started yet, automatically refresh it with any new unassigned orders for this driver's zones
            if not route.is_locked and route.started_at is None:
                unassigned_orders = Order.objects.filter(
                    scheduled_delivery_date=route.delivery_date,
                    status__in=[OrderStatus.PENDING, OrderStatus.CONFIRMED],
                    route_stop__isnull=True,
                    customer__zone__assigned_driver=user,
                )
                if unassigned_orders.exists():
                    from routing.models import Driver
                    driver_profile = Driver.objects.filter(user=user).first()
                    warehouse = driver_profile.warehouse if driver_profile else None
                    warehouse_location = None
                    if warehouse and warehouse.latitude is not None and warehouse.longitude is not None:
                        warehouse_location = {
                            "longitude": float(warehouse.longitude),
                            "latitude": float(warehouse.latitude),
                        }

                    existing_order_ids = list(route.stops.values_list("order_id", flat=True))
                    new_order_ids = list(unassigned_orders.values_list("id", flat=True))
                    all_order_ids = list(set(str(oid) for oid in existing_order_ids) | set(str(noid) for noid in new_order_ids))

                    route = create_optimized_route(
                        route.name,
                        user,
                        route.delivery_date,
                        all_order_ids,
                        warehouse=warehouse,
                        warehouse_location=warehouse_location,
                    )
                    route = (
                        Route.objects.filter(id=route.id)
                        .prefetch_related("stops__order__customer")
                        .first()
                    )

            # If the route is started/in progress, make sure all non-delivered/non-cancelled/undelivered orders are IN_TRANSIT
            elif route.status == RouteStatus.IN_PROGRESS or route.started_at is not None:
                updated_any = False
                for stop in route.stops.all():
                    if stop.order.status in [
                        OrderStatus.PENDING,
                        OrderStatus.CONFIRMED,
                        OrderStatus.DISPATCHED,
                    ]:
                        stop.order.status = OrderStatus.IN_TRANSIT
                        stop.order.save(update_fields=["status"])
                        updated_any = True
                if updated_any:
                    route = (
                        Route.objects.filter(id=route.id)
                        .prefetch_related("stops__order__customer")
                        .first()
                    )

            return Response(RouteSerializer(route).data)

    @action(
        detail=False,
        methods=["post"],
        url_path="start-tracking",
        permission_classes=[IsAuthenticated],
    )
    def start_tracking(self, request):
        """
        Starts a GPS tracking session for the driver.
        Only requires a valid JWT — no group membership needed.
        Auto-creates a Driver profile and Drivers group membership if missing.
        If no route is assigned today, auto-creates a dummy test route
        so WebSocket trail recording works without real orders.
        Returns the route_id to use for the WebSocket session.
        """
        from django_tenants.utils import schema_context
        from django.db import connection
        from django.utils import timezone
        from django.contrib.auth.models import Group
        import datetime

        user = request.user

        # 1. Prevent arbitrary customers from self-promoting to drivers
        if user.is_customer and not (user.is_superuser or user.is_staff):
            return Response(
                {
                    "error": "Access denied. Customers are not allowed to promote themselves to drivers."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # Auto-assign user to Drivers group so future driver endpoints also work
        drivers_group, _ = Group.objects.get_or_create(name="Drivers")
        if not user.groups.filter(name="Drivers").exists():
            user.groups.add(drivers_group)

        # Mark user as driver if not already
        if not user.is_driver:
            user.is_driver = True
            user.save(update_fields=["is_driver"])

        schema = user.tenant_schema
        context_schema = (
            schema
            if connection.schema_name == "public" and schema
            else connection.schema_name
        )

        with schema_context(context_schema):
            from routing.models import Driver, Route, RouteStatus

            # Step 1: Ensure a Driver profile exists for this user
            driver_profile, created_profile = Driver.objects.get_or_create(
                user=user,
                defaults={
                    "vehicle_plate": f"TEST-{user.username[:6].upper()}",
                    "vehicle_type": "van",
                    "is_available": True,
                    "on_trip": False,
                },
            )

            # Step 2: Check if there's already an active/in-progress route today
            from django.db.models import Q

            today = datetime.date.today()
            existing_route = (
                Route.objects.filter(
                    Q(driver=driver_profile) | Q(additional_drivers=driver_profile),
                    is_completed=False,
                    delivery_date=today,
                )
                .distinct()
                .order_by("-created_at")
                .first()
            )

            if existing_route:
                # Already has a route - just mark it as started if not yet
                if existing_route.status != RouteStatus.IN_PROGRESS:
                    existing_route.status = RouteStatus.IN_PROGRESS
                    existing_route.started_at = timezone.now()
                    existing_route.save(update_fields=["status", "started_at"])

                # Ensure all non-delivered/non-cancelled/undelivered orders on this route are set to IN_TRANSIT
                from orders.models import OrderStatus

                for order in existing_route.orders.all():
                    if order.status in [
                        OrderStatus.PENDING,
                        OrderStatus.CONFIRMED,
                        OrderStatus.DISPATCHED,
                    ]:
                        order.status = OrderStatus.IN_TRANSIT
                        order.save(update_fields=["status"])

                driver_profile.is_available = False
                driver_profile.on_trip = True
                driver_profile.save(update_fields=["is_available", "on_trip"])
                return Response(
                    {
                        "detail": "Tracking session started on existing route.",
                        "route_id": str(existing_route.id),
                        "route_name": existing_route.name,
                        "is_test_route": False,
                        "started_at": existing_route.started_at,
                    }
                )

            # Step 3: No route today — auto-create a dummy tracking test route
            dummy_route = Route.objects.create(
                driver=driver_profile,
                name=f'GPS Test — {user.get_full_name() or user.username} — {today.strftime("%d %b %Y")}',
                delivery_date=today,
                status=RouteStatus.IN_PROGRESS,
                started_at=timezone.now(),
                is_test_route=True,
            )

            driver_profile.is_available = False
            driver_profile.on_trip = True
            driver_profile.save(update_fields=["is_available", "on_trip"])

            return Response(
                {
                    "detail": "Dummy tracking route created and trip started. Connect WebSocket and send GPS coordinates.",
                    "route_id": str(dummy_route.id),
                    "route_name": dummy_route.name,
                    "is_test_route": True,
                    "started_at": dummy_route.started_at,
                    "instructions": 'Connect WebSocket: ws://<server>/ws/tracking/?token=<jwt_token> and send {"lat": 21.14, "lng": 79.08}',
                }
            )

    @action(
        detail=False,
        methods=["post"],
        url_path="stop-tracking",
        permission_classes=[IsAuthenticated],
    )
    def stop_tracking(self, request):
        """
        Stops the active GPS tracking session for the driver.
        Marks the active route as completed and frees the driver.
        """
        return Response(
            {"error": "Manual trip tracking completion is disabled. Trips are automatically completed by the system at 12:00 PM."},
            status=400,
        )

    @action(detail=True, methods=["post"], url_path="start-trip")
    def start_trip(self, request, pk=None):
        """
        Starts the route and marks all orders as IN_TRANSIT.
        pk is the Route ID.
        """
        from django_tenants.utils import schema_context
        from django.db import connection

        user = request.user
        schema = user.tenant_schema
        context_schema = (
            schema
            if connection.schema_name == "public" and schema
            else connection.schema_name
        )

        with schema_context(context_schema):
            try:
                route = start_trip_for_route(pk, user)
                if not route:
                    return Response(
                        {"error": f"Route with ID {pk} does not exist in this city."},
                        status=status.HTTP_404_NOT_FOUND,
                    )
                return Response(
                    {
                        "detail": "Trip started successfully.",
                        "started_at": route.started_at,
                    }
                )
            except PermissionError as pe:
                return Response(
                    {"error": "Access Denied", "detail": str(pe)},
                    status=status.HTTP_403_FORBIDDEN,
                )
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="complete-trip")
    def complete_trip(self, request, pk=None):
        """
        Finishes the route.
        pk is the Route ID.
        """
        return Response(
            {"error": "Manual trip completion is disabled. Trips are automatically completed by the system at 12:00 PM."},
            status=400,
        )

    @action(detail=True, methods=["post"], url_path="submit-delivery")
    def submit_delivery(self, request, pk=None):
        """
        One-tap delivery submission for the driver.
        pk is the Order ID.
        """
        from django_tenants.utils import schema_context
        from django.db import connection

        user = request.user
        schema = user.tenant_schema
        context_schema = (
            schema
            if connection.schema_name == "public" and schema
            else connection.schema_name
        )

        with schema_context(context_schema):
            # Logic is similar to OrderViewSet.mark_delivered but optimized for driver context
            order_viewset = OrderViewSet()
            order_viewset.request = request
            order_viewset.action = "submit_delivery"
            order_viewset.get_permissions = lambda: [IsAuthenticated()]
            order_viewset.kwargs = {"pk": pk}
            return order_viewset.mark_delivered(request, pk=pk)

    @action(detail=True, methods=["post"], url_path="submit-undelivered")
    def submit_undelivered(self, request, pk=None):
        """
        Submission for driver to mark order as undelivered (proof of attempt required).
        pk is the Order ID.
        """
        from django_tenants.utils import schema_context
        from django.db import connection

        user = request.user
        schema = user.tenant_schema
        context_schema = (
            schema
            if connection.schema_name == "public" and schema
            else connection.schema_name
        )

        with schema_context(context_schema):
            order_viewset = OrderViewSet()
            order_viewset.request = request
            order_viewset.action = "submit_undelivered"
            order_viewset.get_permissions = lambda: [IsAuthenticated()]
            order_viewset.kwargs = {"pk": pk}
            return order_viewset.mark_undelivered(request, pk=pk)

    @action(
        detail=False,
        methods=["get"],
        url_path="today-summary",
        permission_classes=[IsAuthenticated],
    )
    def today_summary(self, request):
        """
        Returns a consolidated dashboard summary for the logged-in driver for today.
        Includes:
        - Total bottles to carry (by bottle type)
        - Number of special/extra orders
        - Expected bottle returns (outstanding balances from customers on today's route)
        - Total orders count, delivered count, pending count
        - Route info (id, name, status)
        """
        from django_tenants.utils import schema_context
        from django.db import connection
        from collections import defaultdict

        user = request.user
        schema = user.tenant_schema
        context_schema = (
            schema
            if connection.schema_name == "public" and schema
            else connection.schema_name
        )

        with schema_context(context_schema):
            from django.db.models import Q, Count
            import datetime as _dt

            today = _dt.date.today()

            # Find today's active route for this driver (with stops)
            active_route = (
                Route.objects.annotate(stops_count=Count("stops"))
                .filter(
                    Q(driver=user) | Q(additional_drivers=user),
                    delivery_date=today,
                    stops_count__gt=0,
                )
                .distinct()
                .prefetch_related(
                    "stops__order__items__product__bottle_type",
                    "stops__order__customer__bottle_balances__bottle_type",
                )
                .order_by("-created_at")
                .first()
            )

            if not active_route:
                return Response({
                    "date": str(today),
                    "has_route": False,
                    "route": None,
                    "total_orders": 0,
                    "pending_orders": 0,
                    "delivered_orders": 0,
                    "undelivered_orders": 0,
                    "special_orders": 0,
                    "bottles_to_carry": [],
                    "total_bottles_to_carry": 0,
                    "bottles_to_collect": [],
                    "total_bottles_to_collect": 0,
                })

            # Gather all stops and their orders
            stops = active_route.stops.all()
            orders = [stop.order for stop in stops]

            # --- Count order types ---
            total_orders = len(orders)
            special_orders = sum(1 for o in orders if o.is_special)
            delivered_orders = sum(
                1 for o in orders if o.status == OrderStatus.DELIVERED
            )
            undelivered_orders = sum(
                1 for o in orders if o.status == OrderStatus.UNDELIVERED
            )
            pending_orders = total_orders - delivered_orders - undelivered_orders

            # --- Bottles to carry (deliver) by type ---
            bottles_to_carry = defaultdict(lambda: {"name": "", "volume_ml": 0, "quantity": 0})
            for order in orders:
                # Only count bottles for orders that are NOT yet delivered/cancelled/undelivered
                if order.status in [
                    OrderStatus.DELIVERED,
                    OrderStatus.CANCELLED,
                    OrderStatus.UNDELIVERED,
                ]:
                    continue
                for item in order.items.all():
                    product = item.product
                    if product.is_returnable and product.bottle_type:
                        bt = product.bottle_type
                        bottles_to_carry[str(bt.id)]["name"] = bt.name
                        bottles_to_carry[str(bt.id)]["volume_ml"] = bt.volume_ml
                        bottles_to_carry[str(bt.id)]["quantity"] += item.quantity

            bottles_carry_list = [
                {
                    "bottle_type_id": bt_id,
                    "bottle_type_name": data["name"],
                    "volume_ml": data["volume_ml"],
                    "quantity": data["quantity"],
                }
                for bt_id, data in bottles_to_carry.items()
            ]
            total_bottles_to_carry = sum(d["quantity"] for d in bottles_carry_list)

            # --- Bottles to collect (returns) — outstanding customer balances ---
            bottles_to_collect = defaultdict(lambda: {"name": "", "volume_ml": 0, "quantity": 0})
            seen_customers = set()
            for order in orders:
                cust = order.customer
                if cust.id in seen_customers:
                    continue
                seen_customers.add(cust.id)
                for bal in cust.bottle_balances.all():
                    if bal.balance > 0:
                        bt = bal.bottle_type
                        bottles_to_collect[str(bt.id)]["name"] = bt.name
                        bottles_to_collect[str(bt.id)]["volume_ml"] = bt.volume_ml
                        bottles_to_collect[str(bt.id)]["quantity"] += bal.balance

            bottles_collect_list = [
                {
                    "bottle_type_id": bt_id,
                    "bottle_type_name": data["name"],
                    "volume_ml": data["volume_ml"],
                    "quantity": data["quantity"],
                }
                for bt_id, data in bottles_to_collect.items()
            ]
            total_bottles_to_collect = sum(d["quantity"] for d in bottles_collect_list)

            return Response({
                "date": str(today),
                "has_route": True,
                "route": {
                    "id": str(active_route.id),
                    "name": active_route.name,
                    "status": active_route.status,
                    "is_completed": active_route.is_completed,
                    "started_at": active_route.started_at,
                    "delivery_date": str(active_route.delivery_date),
                },
                "total_orders": total_orders,
                "pending_orders": pending_orders,
                "delivered_orders": delivered_orders,
                "undelivered_orders": undelivered_orders,
                "special_orders": special_orders,
                "bottles_to_carry": bottles_carry_list,
                "total_bottles_to_carry": total_bottles_to_carry,
                "bottles_to_collect": bottles_collect_list,
            })

    @action(
        detail=False,
        methods=["get"],
        url_path="today_summary",
        permission_classes=[IsAuthenticated],
    )
    def today_summary_underscore(self, request):
        """
        Alias for today_summary.
        """
        return self.today_summary(request)

    @action(detail=False, methods=["get"], url_path="resolve-qr/(?P<qr_id>[^/.]+)")
    def resolve_qr(self, request, qr_id=None):
        """
        Fetches customer details and today's pending order by QR Code ID.
        """
        from django_tenants.utils import schema_context
        from django.db import connection

        user = request.user
        schema = user.tenant_schema
        context_schema = (
            schema
            if connection.schema_name == "public" and schema
            else connection.schema_name
        )

        with schema_context(context_schema):
            from crm.models import Customer
            from crm.serializers import CustomerSerializer
            from inventory.models import CustomerBottleBalance

            customer = Customer.objects.filter(qr_code_id=qr_id).first()
            if not customer:
                return Response({"detail": "Invalid QR Code."}, status=404)

            # Get today's pending order for this customer
            today = datetime.date.today()
            order = Order.objects.filter(
                customer=customer,
                scheduled_delivery_date=today,
                status__in=[
                    OrderStatus.PENDING,
                    OrderStatus.CONFIRMED,
                    OrderStatus.DISPATCHED,
                    OrderStatus.IN_TRANSIT,
                ],
            ).first()

            # Get bottle balances
            balances = CustomerBottleBalance.objects.filter(customer=customer)
            balance_data = [
                {"bottle_type": b.bottle_type.name, "balance": b.balance}
                for b in balances
            ]

            return Response(
                {
                    "customer": CustomerSerializer(customer).data,
                    "order": OrderSerializer(order).data if order else None,
                    "bottle_balances": balance_data,
                }
            )
