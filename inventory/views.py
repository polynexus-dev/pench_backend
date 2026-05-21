from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from core.permissions import IsERPUser, HasGroupPermission
from .models import Product, Stock, Warehouse, BottleType, CustomerBottleBalance, BottleTransaction, CustomerProductPrice
from .serializers import (
    ProductSerializer, StockSerializer, WarehouseSerializer,
    BottleTypeSerializer, BottleTransactionSerializer, CustomerBottleBalanceSerializer,
    CustomerProductPriceSerializer
)


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all().select_related('bottle_type')
    serializer_class = ProductSerializer
    permission_classes = [IsERPUser, HasGroupPermission]
    required_groups = ['Inventory_Managers', 'ERP_Admins']
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
    permission_classes = [IsERPUser, HasGroupPermission]
    required_groups = ['Inventory_Managers', 'ERP_Admins']
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

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        """
        Returns a global summary of returnable bottles and a driver-wise breakdown.
        """
        import datetime
        from django.db.models import Sum
        from inventory.models import BottleType, CustomerBottleBalance, BottleTransaction, BottleTransactionType
        from routing.models import Route, Driver
        from orders.models import Order, OrderItem

        # 1. Fetch active Bottle Types
        bottle_types = BottleType.objects.filter(is_active=True)
        
        # 2. Resolve target date (default to today)
        today = datetime.date.today()
        date_str = request.query_params.get('date')
        if date_str:
            try:
                today = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        # 3. Calculate Global Summary statistics
        global_summary = []
        for bt in bottle_types:
            # Current with customers (sum of balances)
            total_with_customers = CustomerBottleBalance.objects.filter(
                bottle_type=bt
            ).aggregate(total=Sum('balance'))['total'] or 0

            # Total lost / broken
            total_lost_broken = BottleTransaction.objects.filter(
                bottle_type=bt,
                transaction_type=BottleTransactionType.BROKEN
            ).aggregate(total=Sum('quantity'))['total'] or 0

            # Active routes for the day
            routes_today = Route.objects.filter(delivery_date=today)
            order_ids_today = []
            for r in routes_today:
                order_ids_today.extend(r.orders.values_list('id', flat=True))

            # Dispatched (expected to be delivered today based on items)
            total_dispatched_today = OrderItem.objects.filter(
                order_id__in=order_ids_today,
                product__is_returnable=True,
                product__bottle_type=bt
            ).aggregate(total=Sum('quantity'))['total'] or 0

            # Returned today
            total_returned_today = BottleTransaction.objects.filter(
                bottle_type=bt,
                transaction_type=BottleTransactionType.RETURNED,
                order_id__in=order_ids_today
            ).aggregate(total=Sum('quantity'))['total'] or 0

            global_summary.append({
                'bottle_type_id': str(bt.id),
                'bottle_type_name': bt.name,
                'total_with_customers': total_with_customers,
                'total_lost_broken': total_lost_broken,
                'total_dispatched_today': total_dispatched_today,
                'total_returned_today': total_returned_today,
            })

        # 4. Calculate Driver Breakdown
        driver_breakdown = []
        routes_today = Route.objects.filter(delivery_date=today).select_related('driver__user')
        
        for route in routes_today:
            driver_profile = route.driver
            driver_user = driver_profile.user if driver_profile else None
            driver_name = driver_user.get_full_name() if driver_user else (driver_user.username if driver_user else "Unassigned")
            vehicle_plate = driver_profile.vehicle_plate if driver_profile else "N/A"
            
            route_order_ids = list(route.orders.values_list('id', flat=True))
            
            bottles_stats = []
            for bt in bottle_types:
                # Dispatched (loaded on truck)
                dispatched = OrderItem.objects.filter(
                    order_id__in=route_order_ids,
                    product__is_returnable=True,
                    product__bottle_type=bt
                ).aggregate(total=Sum('quantity'))['total'] or 0
                
                # Delivered (issued to customers)
                delivered = BottleTransaction.objects.filter(
                    bottle_type=bt,
                    transaction_type=BottleTransactionType.ISSUED,
                    order_id__in=route_order_ids
                ).aggregate(total=Sum('quantity'))['total'] or 0
                
                # Returned (collected empty)
                returned = BottleTransaction.objects.filter(
                    bottle_type=bt,
                    transaction_type=BottleTransactionType.RETURNED,
                    order_id__in=route_order_ids
                ).aggregate(total=Sum('quantity'))['total'] or 0
                
                # Broken/lost on trip
                broken = BottleTransaction.objects.filter(
                    bottle_type=bt,
                    transaction_type=BottleTransactionType.BROKEN,
                    order_id__in=route_order_ids
                ).aggregate(total=Sum('quantity'))['total'] or 0
                
                if dispatched > 0 or returned > 0 or broken > 0 or delivered > 0:
                    bottles_stats.append({
                        'bottle_type_id': str(bt.id),
                        'bottle_type_name': bt.name,
                        'dispatched': dispatched,
                        'delivered': delivered,
                        'returned': returned,
                        'broken': broken,
                        'remaining_full': max(0, dispatched - delivered),
                    })
            
            driver_breakdown.append({
                'route_id': str(route.id),
                'route_name': route.name,
                'route_status': route.status,
                'route_status_display': route.get_status_display(),
                'driver_name': driver_name,
                'vehicle_plate': vehicle_plate,
                'bottles': bottles_stats
            })

        return Response({
            'date': today.isoformat(),
            'global_summary': global_summary,
            'driver_breakdown': driver_breakdown
        })



class CustomerBottleBalanceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = CustomerBottleBalance.objects.select_related('customer', 'bottle_type')
    serializer_class = CustomerBottleBalanceSerializer
    permission_classes = [IsERPUser]
    filterset_fields = ['customer', 'bottle_type']


class CustomerProductPriceViewSet(viewsets.ModelViewSet):
    queryset = CustomerProductPrice.objects.select_related('customer', 'product')
    serializer_class = CustomerProductPriceSerializer
    permission_classes = [IsERPUser]
    filterset_fields = ['customer', 'product']

