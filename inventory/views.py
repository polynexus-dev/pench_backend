from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from core.permissions import IsERPUser, HasGroupPermission, IsDriverUser
from .models import (
    Product,
    RawMaterial,
    Stock,
    Warehouse,
    BottleType,
    CustomerBottleBalance,
    BottleTransaction,
    CustomerProductPrice,
    StockMovement,
)
from .serializers import (
    ProductSerializer,
    RawMaterialSerializer,
    StockSerializer,
    WarehouseSerializer,
    BottleTypeSerializer,
    BottleTransactionSerializer,
    CustomerBottleBalanceSerializer,
    CustomerProductPriceSerializer,
    StockMovementSerializer,
)


class RawMaterialViewSet(viewsets.ModelViewSet):
    queryset = RawMaterial.objects.all()
    serializer_class = RawMaterialSerializer
    permission_classes = [IsERPUser]
    search_fields = ["name", "sku"]


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all().select_related("bottle_type")
    serializer_class = ProductSerializer
    permission_classes = [IsERPUser, HasGroupPermission]
    required_groups = ["Inventory_Managers", "ERP_Admins"]
    search_fields = ["name", "sku"]

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            from rest_framework.permissions import IsAuthenticated
            return [IsAuthenticated()]
        return super().get_permissions()


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
        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )

    @action(detail=False, methods=["patch", "put"])
    def bulk_update(self, request):
        """
        Updates multiple products at once. Each object must have an 'id'.
        """
        data = request.data
        if not isinstance(data, list):
            return Response(
                {"detail": "Expected a list of objects."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        updated_products = []
        for item in data:
            product_id = item.get("id")
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
    queryset = Stock.objects.select_related("raw_material", "warehouse")
    serializer_class = StockSerializer
    permission_classes = [IsERPUser, HasGroupPermission]
    required_groups = ["Inventory_Managers", "ERP_Admins"]
    filterset_fields = ["warehouse", "raw_material"]

    @action(detail=False, methods=["patch", "put"])
    def bulk_update(self, request):
        """
        Updates stock levels for multiple items. Each object must have an 'id'.
        """
        data = request.data
        if not isinstance(data, list):
            return Response(
                {"detail": "Expected a list."}, status=status.HTTP_400_BAD_REQUEST
            )

        updated = []
        for item in data:
            stock_id = item.get("id")
            if not stock_id:
                continue
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

    @action(detail=True, methods=["get"], url_path="forecast")
    def forecast(self, request, pk=None):
        """
        Subscription-aware demand forecasting engine.

        3-tier demand calculation per date:
          Tier 1: Routes exist for this warehouse+date → aggregate from route orders (most accurate)
          Tier 2: Orders exist for the date but no routes yet → aggregate from pending orders
          Tier 3: No orders generated yet → predict from active subscriptions using should_deliver_on()

        Returns a 3-day horizon: today, tomorrow, day_after_tomorrow.
        """
        import datetime
        from django.db.models import Sum, Q
        from orders.models import Order, OrderItem, OrderStatus
        from routing.models import Route
        from subscriptions.models import (
            Subscription,
            SubscriptionStatus,
            SubscriptionItem,
        )

        warehouse = self.get_object()
        today = datetime.date.today()
        tomorrow = today + datetime.timedelta(days=1)
        day_after = today + datetime.timedelta(days=2)

        # Fetch all stock items registered for this warehouse
        stock_qs = Stock.objects.filter(warehouse=warehouse).select_related(
            "raw_material"
        )

        def calculate_demand(target_date):
            """
            3-tier demand calculation for a single date.
            Returns dict of {product_id: quantity} and a string indicating the source tier.
            """
            # Tier 1: Check if routes have been generated for this warehouse + date
            routes = Route.objects.filter(
                warehouse=warehouse, delivery_date=target_date
            )
            if routes.exists():
                order_ids = []
                for r in routes:
                    order_ids.extend(r.orders.values_list("id", flat=True))

                if order_ids:
                    demand = (
                        OrderItem.objects.filter(order_id__in=order_ids)
                        .values("product_id")
                        .annotate(total_qty=Sum("quantity"))
                    )
                    return {
                        item["product_id"]: item["total_qty"] for item in demand
                    }, "routes"

            # Tier 2: Check if orders exist for this date (but routes not generated yet)
            pending_orders = Order.objects.filter(
                scheduled_delivery_date=target_date,
                status__in=[OrderStatus.PENDING, OrderStatus.CONFIRMED],
            )
            if pending_orders.exists():
                demand = (
                    OrderItem.objects.filter(order__in=pending_orders)
                    .values("product_id")
                    .annotate(total_qty=Sum("quantity"))
                )
                return {
                    item["product_id"]: item["total_qty"] for item in demand
                }, "orders"

            # Tier 3: No orders yet — predict from active subscriptions
            active_subs = Subscription.objects.filter(
                status=SubscriptionStatus.ACTIVE, start_date__lte=target_date
            ).prefetch_related("items__product")

            predicted_demand = {}
            for sub in active_subs:
                # Check end date
                if sub.end_date and sub.end_date < target_date:
                    continue
                # Check skip dates
                if sub.skip_dates.filter(skip_date=target_date).exists():
                    continue
                # Check frequency logic
                if not sub.should_deliver_on(target_date):
                    continue

                for item in sub.items.all():
                    pid = item.product_id
                    predicted_demand[pid] = predicted_demand.get(pid, 0) + item.quantity

            return predicted_demand, "subscriptions"

        # Calculate demand for all 3 days
        today_demands, today_source = calculate_demand(today)
        tomorrow_demands, tomorrow_source = calculate_demand(tomorrow)
        day_after_demands, day_after_source = calculate_demand(day_after)

        # Calculate dispatched today (already delivered orders)
        dispatched_today_orders = Order.objects.filter(
            scheduled_delivery_date=today,
            status__in=[
                OrderStatus.DELIVERED,
                OrderStatus.DISPATCHED,
                OrderStatus.IN_TRANSIT,
            ],
        )
        dispatched_items = (
            OrderItem.objects.filter(order__in=dispatched_today_orders)
            .values("product_id")
            .annotate(total_qty=Sum("quantity"))
        )
        dispatched_map = {
            item["product_id"]: item["total_qty"] for item in dispatched_items
        }

        # Perform Derived Demand Rollups to Raw Materials
        from inventory.models import (
            RawMaterial as RawMaterialModel,
            Product as ProductModel,
        )

        raw_materials = {
            rm.id: rm for rm in RawMaterialModel.objects.filter(is_active=True)
        }
        all_products = {
            p.id: p
            for p in ProductModel.objects.filter(is_active=True).select_related(
                "bottle_type"
            )
        }

        # Initialize demands mapped directly to raw material IDs
        raw_today_demands = {}
        raw_tomorrow_demands = {}
        raw_day_after_demands = {}
        raw_dispatched_map = {}

        for pid, product in all_products.items():
            raw_mat = product.raw_material
            if not raw_mat:
                continue
            rm_id = raw_mat.id

            vol_ml = (
                product.bottle_type.volume_ml
                if (product.bottle_type and product.is_returnable)
                else 1000
            )
            conversion_factor = (
                float(vol_ml) / 1000.0 if raw_mat.unit.lower() == "litre" else 1.0
            )

            if pid in today_demands:
                raw_today_demands[rm_id] = raw_today_demands.get(rm_id, 0.0) + (
                    today_demands[pid] * conversion_factor
                )
            if pid in tomorrow_demands:
                raw_tomorrow_demands[rm_id] = raw_tomorrow_demands.get(rm_id, 0.0) + (
                    tomorrow_demands[pid] * conversion_factor
                )
            if pid in day_after_demands:
                raw_day_after_demands[rm_id] = raw_day_after_demands.get(rm_id, 0.0) + (
                    day_after_demands[pid] * conversion_factor
                )
            if pid in dispatched_map:
                raw_dispatched_map[rm_id] = raw_dispatched_map.get(rm_id, 0.0) + (
                    dispatched_map[pid] * conversion_factor
                )

        # Build stock lookup mapped to raw materials
        stock_map = {s.raw_material_id: s for s in stock_qs if s.raw_material_id}

        forecast_data = []
        for rm in raw_materials.values():
            stock_entry = stock_map.get(rm.id)
            if stock_entry:
                current_stock = stock_entry.quantity
                reorder_level = stock_entry.reorder_level
            else:
                current_stock = 0
                reorder_level = 0

            today_qty = int(round(raw_today_demands.get(rm.id, 0.0)))
            tomorrow_qty = int(round(raw_tomorrow_demands.get(rm.id, 0.0)))
            day_after_qty = int(round(raw_day_after_demands.get(rm.id, 0.0)))
            dispatched_qty = int(round(raw_dispatched_map.get(rm.id, 0.0)))

            # Pending today = today's total demand - what's already dispatched
            pending_today = max(0, today_qty - dispatched_qty)

            # Projected balance = current stock - pending today - tomorrow - day after
            projected_balance = (
                current_stock - pending_today - tomorrow_qty - day_after_qty
            )

            # Order recommendation: how much to procure to stay above reorder level
            order_recommendation = max(
                0,
                (pending_today + tomorrow_qty + day_after_qty + reorder_level)
                - current_stock,
            )

            # Stock health status
            if projected_balance >= reorder_level:
                stock_health = "healthy"
            elif current_stock - pending_today - tomorrow_qty >= 0:
                stock_health = "warning"
            else:
                stock_health = "critical"

            forecast_data.append(
                {
                    "product_id": str(rm.id),
                    "product_name": rm.name,
                    "product_sku": rm.sku,
                    "product_unit": rm.unit,
                    "current_stock": current_stock,
                    "reorder_level": reorder_level,
                    "dispatched_today": dispatched_qty,
                    "pending_today": pending_today,
                    "tomorrow_demand": tomorrow_qty,
                    "day_after_demand": day_after_qty,
                    "projected_balance": projected_balance,
                    "order_recommendation": order_recommendation,
                    "stock_health": stock_health,
                    "bottle_volume_l": None,  # direct raw unit reporting, no stacked literal required
                    "demand_sources": {
                        "today": today_source,
                        "tomorrow": tomorrow_source,
                        "day_after": day_after_source,
                    },
                }
            )

        # Sort: critical first, then warning, then healthy
        health_order = {"critical": 0, "warning": 1, "healthy": 2}
        forecast_data.sort(key=lambda x: health_order.get(x["stock_health"], 3))

        return Response(
            {
                "warehouse_id": str(warehouse.id),
                "warehouse_name": warehouse.name,
                "forecast_date": str(today),
                "forecast": forecast_data,
            }
        )

    @action(detail=True, methods=["get"], url_path="history")
    def history(self, request, pk=None):
        """
        Lists stock movements history for this warehouse.
        """
        warehouse = self.get_object()
        movements = StockMovement.objects.filter(warehouse=warehouse).select_related(
            "raw_material", "recorded_by"
        )
        serializer = StockMovementSerializer(movements, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="adjust-stock")
    def adjust_stock(self, request, pk=None):
        """
        Records manual adjustments or inbound replenishments and updates active stock levels in a transaction.
        """
        from django.db import transaction

        warehouse = self.get_object()

        # Accept 'raw_material' or fallback to 'product' so frontend works seamlessly
        raw_material_id = request.data.get("raw_material") or request.data.get(
            "product"
        )
        quantity = request.data.get("quantity")
        movement_type = request.data.get("movement_type")  # inbound or adjustment
        reference = request.data.get("reference", "")
        notes = request.data.get("notes", "")

        if not raw_material_id or quantity is None or not movement_type:
            return Response(
                {
                    "detail": 'Fields "raw_material", "quantity", and "movement_type" are required.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            qty_int = int(quantity)
        except ValueError:
            return Response(
                {"detail": "Quantity must be a valid integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if movement_type not in ["inbound", "adjustment"]:
            return Response(
                {
                    "detail": 'Only "inbound" or "adjustment" movement types can be logged manually.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            raw_material = RawMaterial.objects.get(id=raw_material_id)
        except (RawMaterial.DoesNotExist, ValueError):
            return Response(
                {"detail": "Invalid raw material identifier."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            # Get or create stock record for raw_material/warehouse
            stock, created = Stock.objects.get_or_create(
                warehouse=warehouse,
                raw_material=raw_material,
                defaults={"quantity": 0, "reorder_level": 10},
            )

            # Update stock quantity
            if movement_type == "inbound":
                if qty_int < 0:
                    return Response(
                        {"detail": "Inbound shipments must have a positive quantity."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                stock.quantity += qty_int
            else:  # adjustment
                stock.quantity += qty_int

            # Quantity cannot go below zero
            if stock.quantity < 0:
                stock.quantity = 0

            stock.save()

            # Record stock movement log
            movement = StockMovement.objects.create(
                warehouse=warehouse,
                raw_material=raw_material,
                movement_type=movement_type,
                quantity=qty_int,
                reference=reference,
                notes=notes,
                recorded_by=request.user if not request.user.is_anonymous else None,
            )

        return Response(
            {
                "detail": "Stock level updated successfully.",
                "current_stock": stock.quantity,
                "movement": StockMovementSerializer(movement).data,
            },
            status=status.HTTP_200_OK,
        )


class BottleTypeViewSet(viewsets.ModelViewSet):
    queryset = BottleType.objects.all()
    serializer_class = BottleTypeSerializer

    def get_permissions(self):
        if self.request.method in ["GET", "HEAD", "OPTIONS"]:
            return [(IsERPUser | IsDriverUser)()]
        return [IsERPUser()]


class BottleTransactionViewSet(viewsets.ModelViewSet):
    queryset = BottleTransaction.objects.select_related(
        "bottle_type", "customer", "order", "recorded_by"
    )
    serializer_class = BottleTransactionSerializer
    permission_classes = [IsERPUser]
    filterset_fields = ["customer", "bottle_type", "transaction_type"]

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

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        """
        Returns a global summary of returnable bottles and a driver-wise breakdown.
        """
        import datetime
        from django.db.models import Sum
        from inventory.models import (
            BottleType,
            CustomerBottleBalance,
            BottleTransaction,
            BottleTransactionType,
        )
        from orders.models import Route, Order, OrderItem, RouteStop

        # 1. Fetch active Bottle Types
        bottle_types = BottleType.objects.filter(is_active=True)

        # 2. Resolve target date (default to today, unless "all" or "YYYY-MM" is requested)
        today = datetime.date.today()
        date_str = request.query_params.get("date")
        is_all_time = date_str == "all"
        
        is_month_filter = False
        start_date = None
        end_date = None
        
        if date_str and not is_all_time:
            if len(date_str) == 7 and date_str[4] == "-":
                try:
                    parts = date_str.split("-")
                    year = int(parts[0])
                    month = int(parts[1])
                    start_date = datetime.date(year, month, 1)
                    if month == 12:
                        end_date = datetime.date(year + 1, 1, 1) - datetime.timedelta(days=1)
                    else:
                        end_date = datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)
                    is_month_filter = True
                except ValueError:
                    pass
            else:
                try:
                    today = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                except ValueError:
                    pass

        warehouse_id = request.query_params.get("warehouse")

        # 3. Pre-fetch and aggregate data to prevent N+1 queries
        customer_balances = CustomerBottleBalance.objects.values('bottle_type_id').annotate(total=Sum('balance'))
        balances_map = {str(item['bottle_type_id']): item['total'] for item in customer_balances}

        lost_broken = BottleTransaction.objects.filter(
            transaction_type=BottleTransactionType.BROKEN
        ).values('bottle_type_id').annotate(total=Sum('quantity'))
        lost_broken_map = {str(item['bottle_type_id']): item['total'] for item in lost_broken}

        dispatched_map = {}
        returned_map = {}

        if is_all_time:
            dispatched_qs = OrderItem.objects.filter(
                order__route_stop__route__isnull=False,
                product__is_returnable=True,
            )
            if warehouse_id:
                dispatched_qs = dispatched_qs.filter(order__route_stop__route__warehouse_id=warehouse_id)
            dispatched_totals = dispatched_qs.values('product__bottle_type_id').annotate(total=Sum('quantity'))
            dispatched_map = {str(item['product__bottle_type_id']): item['total'] for item in dispatched_totals}

            returned_qs = BottleTransaction.objects.filter(
                transaction_type=BottleTransactionType.RETURNED,
            )
            if warehouse_id:
                returned_qs = returned_qs.filter(order__route_stop__route__warehouse_id=warehouse_id)
            returned_totals = returned_qs.values('bottle_type_id').annotate(total=Sum('quantity'))
            returned_map = {str(item['bottle_type_id']): item['total'] for item in returned_totals}
        elif is_month_filter:
            dispatched_qs = OrderItem.objects.filter(
                order__route_stop__route__delivery_date__range=(start_date, end_date),
                product__is_returnable=True,
            )
            if warehouse_id:
                dispatched_qs = dispatched_qs.filter(order__route_stop__route__warehouse_id=warehouse_id)
            dispatched_totals = dispatched_qs.values('product__bottle_type_id').annotate(total=Sum('quantity'))
            dispatched_map = {str(item['product__bottle_type_id']): item['total'] for item in dispatched_totals}

            returned_qs = BottleTransaction.objects.filter(
                transaction_type=BottleTransactionType.RETURNED,
                order__route_stop__route__delivery_date__range=(start_date, end_date),
            )
            if warehouse_id:
                returned_qs = returned_qs.filter(order__route_stop__route__warehouse_id=warehouse_id)
            returned_totals = returned_qs.values('bottle_type_id').annotate(total=Sum('quantity'))
            returned_map = {str(item['bottle_type_id']): item['total'] for item in returned_totals}
        else:
            routes_today = Route.objects.filter(delivery_date=today)
            if warehouse_id:
                routes_today = routes_today.filter(warehouse_id=warehouse_id)
            order_ids_today = list(RouteStop.objects.filter(route__in=routes_today).values_list("order_id", flat=True))

            dispatched_qs = OrderItem.objects.filter(
                order_id__in=order_ids_today,
                product__is_returnable=True,
            ).values('product__bottle_type_id').annotate(total=Sum('quantity'))
            dispatched_map = {str(item['product__bottle_type_id']): item['total'] for item in dispatched_qs}

            returned_qs = BottleTransaction.objects.filter(
                transaction_type=BottleTransactionType.RETURNED,
                order_id__in=order_ids_today,
            ).values('bottle_type_id').annotate(total=Sum('quantity'))
            returned_map = {str(item['bottle_type_id']): item['total'] for item in returned_qs}

        global_summary = []
        for bt in bottle_types:
            bt_id = str(bt.id)
            global_summary.append(
                {
                    "bottle_type_id": bt_id,
                    "bottle_type_name": bt.name,
                    "total_with_customers": balances_map.get(bt_id, 0),
                    "total_lost_broken": lost_broken_map.get(bt_id, 0),
                    "total_dispatched_today": dispatched_map.get(bt_id, 0),
                    "total_returned_today": returned_map.get(bt_id, 0),
                }
            )

        # 4. Calculate Driver Breakdown
        driver_breakdown = []
        if is_all_time or is_month_filter:
            from accounts.models import User
            drivers = User.objects.filter(groups__name="Drivers")
            
            routes_qs = Route.objects.filter(driver__in=drivers)
            if is_month_filter:
                routes_qs = routes_qs.filter(delivery_date__range=(start_date, end_date))
            if warehouse_id:
                routes_qs = routes_qs.filter(warehouse_id=warehouse_id)
            
            route_driver_map = {str(r.id): r.driver_id for r in routes_qs}
            routes_list = list(routes_qs)

            dispatched_data = OrderItem.objects.filter(
                order__route_stop__route__in=routes_list,
                product__is_returnable=True
            ).values(
                'order__route_stop__route_id', 'product__bottle_type_id'
            ).annotate(
                total=Sum('quantity')
            )

            tx_data = BottleTransaction.objects.filter(
                order__route_stop__route__in=routes_list
            ).values(
                'order__route_stop__route_id', 'bottle_type_id', 'transaction_type'
            ).annotate(
                total=Sum('quantity')
            )

            driver_dispatched = {}
            for item in dispatched_data:
                r_id = str(item['order__route_stop__route_id'])
                bt_id = str(item['product__bottle_type_id'])
                d_id = str(route_driver_map.get(r_id))
                if d_id:
                    driver_dispatched[(d_id, bt_id)] = driver_dispatched.get((d_id, bt_id), 0) + item['total']

            driver_tx = {}
            for item in tx_data:
                r_id = str(item['order__route_stop__route_id'])
                bt_id = str(item['bottle_type_id'])
                tx_type = item['transaction_type']
                d_id = str(route_driver_map.get(r_id))
                if d_id:
                    driver_tx[(d_id, bt_id, tx_type)] = driver_tx.get((d_id, bt_id, tx_type), 0) + item['total']

            for driver in drivers:
                d_id = str(driver.id)
                bottles_stats = []
                for bt in bottle_types:
                    bt_id = str(bt.id)
                    dispatched = driver_dispatched.get((d_id, bt_id), 0)
                    delivered = driver_tx.get((d_id, bt_id, BottleTransactionType.ISSUED), 0)
                    returned = driver_tx.get((d_id, bt_id, BottleTransactionType.RETURNED), 0)
                    broken = driver_tx.get((d_id, bt_id, BottleTransactionType.BROKEN), 0)

                    if dispatched > 0 or returned > 0 or broken > 0 or delivered > 0:
                        bottles_stats.append(
                            {
                                "bottle_type_id": bt_id,
                                "bottle_type_name": bt.name,
                                "dispatched": dispatched,
                                "delivered": delivered,
                                "returned": returned,
                                "broken": broken,
                                "remaining_full": max(0, dispatched - delivered),
                            }
                        )

                if bottles_stats:
                    driver_breakdown.append(
                        {
                            "route_id": d_id,
                            "route_name": "All-Time Summary" if is_all_time else f"Monthly Summary ({date_str})",
                            "route_status": "completed",
                            "route_status_display": "All-Time" if is_all_time else "Monthly",
                            "driver_id": d_id,
                            "driver_warehouse_id": str(driver.warehouse.id) if driver.warehouse else None,
                            "driver_warehouse_name": driver.warehouse.name if driver.warehouse else "No Warehouse",
                            "driver_name": driver.get_full_name() or driver.username,
                            "vehicle_plate": getattr(getattr(driver, "driver_profile", None), "vehicle_plate", "N/A"),
                            "bottles": bottles_stats,
                        }
                    )
        else:
            routes_today = Route.objects.filter(delivery_date=today).select_related(
                "driver", "driver__driver_profile"
            )
            if warehouse_id:
                routes_today = routes_today.filter(warehouse_id=warehouse_id)

            routes_list = list(routes_today)

            dispatched_data = OrderItem.objects.filter(
                order__route_stop__route__in=routes_list,
                product__is_returnable=True
            ).values(
                'order__route_stop__route_id', 'product__bottle_type_id'
            ).annotate(
                total=Sum('quantity')
            )

            tx_data = BottleTransaction.objects.filter(
                order__route_stop__route__in=routes_list
            ).values(
                'order__route_stop__route_id', 'bottle_type_id', 'transaction_type'
            ).annotate(
                total=Sum('quantity')
            )

            route_dispatched = {}
            for item in dispatched_data:
                r_id = str(item['order__route_stop__route_id'])
                bt_id = str(item['product__bottle_type_id'])
                route_dispatched[(r_id, bt_id)] = item['total']

            route_tx = {}
            for item in tx_data:
                r_id = str(item['order__route_stop__route_id'])
                bt_id = str(item['bottle_type_id'])
                tx_type = item['transaction_type']
                route_tx[(r_id, bt_id, tx_type)] = item['total']

            for route in routes_list:
                r_id = str(route.id)
                driver_user = route.driver
                driver_name = (
                    driver_user.get_full_name()
                    if driver_user
                    else (driver_user.username if driver_user else "Unassigned")
                )
                vehicle_plate = "N/A"
                if driver_user and hasattr(driver_user, "driver_profile"):
                    vehicle_plate = driver_user.driver_profile.vehicle_plate

                bottles_stats = []
                for bt in bottle_types:
                    bt_id = str(bt.id)
                    dispatched = route_dispatched.get((r_id, bt_id), 0)
                    delivered = route_tx.get((r_id, bt_id, BottleTransactionType.ISSUED), 0)
                    returned = route_tx.get((r_id, bt_id, BottleTransactionType.RETURNED), 0)
                    broken = route_tx.get((r_id, bt_id, BottleTransactionType.BROKEN), 0)

                    if dispatched > 0 or returned > 0 or broken > 0 or delivered > 0:
                        bottles_stats.append(
                            {
                                "bottle_type_id": bt_id,
                                "bottle_type_name": bt.name,
                                "dispatched": dispatched,
                                "delivered": delivered,
                                "returned": returned,
                                "broken": broken,
                                "remaining_full": max(0, dispatched - delivered),
                            }
                        )

                driver_breakdown.append(
                    {
                        "route_id": r_id,
                        "route_name": route.name,
                        "route_status": route.status,
                        "route_status_display": route.get_status_display(),
                        "driver_id": str(route.driver.id) if route.driver else None,
                        "driver_warehouse_id": (
                            str(route.driver.warehouse.id)
                            if (route.driver and route.driver.warehouse)
                            else None
                        ),
                        "driver_warehouse_name": (
                            route.driver.warehouse.name
                            if (route.driver and route.driver.warehouse)
                            else "No Warehouse"
                        ),
                        "driver_name": driver_name,
                        "vehicle_plate": vehicle_plate,
                        "bottles": bottles_stats,
                    }
                )

        response_data = {
            "date": "all" if is_all_time else (date_str if is_month_filter else today.isoformat()),
            "global_summary": global_summary,
            "driver_breakdown": driver_breakdown,
        }

        # 5. Month-wise summary trend if "all" time is requested
        if is_all_time:
            from django.db.models.functions import TruncMonth
            
            dispatched_by_month = OrderItem.objects.filter(
                order__route_stop__route__isnull=False,
                product__is_returnable=True
            )
            if warehouse_id:
                dispatched_by_month = dispatched_by_month.filter(order__route_stop__route__warehouse_id=warehouse_id)
                
            dispatched_by_month = (
                dispatched_by_month.annotate(month=TruncMonth("order__route_stop__route__delivery_date"))
                .values("month")
                .annotate(total=Sum("quantity"))
                .order_by("month")
            )

            returned_by_month = BottleTransaction.objects.filter(
                transaction_type=BottleTransactionType.RETURNED
            )
            if warehouse_id:
                returned_by_month = returned_by_month.filter(order__route_stop__route__warehouse_id=warehouse_id)
                
            returned_by_month = (
                returned_by_month.annotate(month=TruncMonth("created_at"))
                .values("month")
                .annotate(total=Sum("quantity"))
                .order_by("month")
            )

            months_data = {}
            for item in dispatched_by_month:
                m = item["month"]
                if m:
                    m_str = m.strftime("%Y-%m")
                    if m_str not in months_data:
                        months_data[m_str] = {
                            "date": m_str,
                            "dispatched": 0,
                            "returned": 0,
                            "with_customers": 0,
                            "lost_broken": 0
                        }
                    months_data[m_str]["dispatched"] = item["total"]

            for item in returned_by_month:
                m = item["month"]
                if m:
                    m_str = m.strftime("%Y-%m")
                    if m_str not in months_data:
                        months_data[m_str] = {
                            "date": m_str,
                            "dispatched": 0,
                            "returned": 0,
                            "with_customers": 0,
                            "lost_broken": 0
                        }
                    months_data[m_str]["returned"] = item["total"]

            response_data["history_trend"] = sorted(months_data.values(), key=lambda x: x["date"])

        return Response(response_data)


class CustomerBottleBalanceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = CustomerBottleBalance.objects.select_related("customer", "bottle_type")
    serializer_class = CustomerBottleBalanceSerializer
    permission_classes = [IsERPUser]
    filterset_fields = ["customer", "bottle_type"]


class CustomerProductPriceViewSet(viewsets.ModelViewSet):
    queryset = CustomerProductPrice.objects.select_related("customer", "product")
    serializer_class = CustomerProductPriceSerializer
    permission_classes = [IsERPUser]
    filterset_fields = ["customer", "product"]
