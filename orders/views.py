from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from core.permissions import IsERPUser
from .models import Order, OrderStatus, Route
from .serializers import OrderSerializer, RouteSerializer
from .services import create_optimized_route


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.select_related('customer').prefetch_related('items')
    serializer_class = OrderSerializer
    permission_classes = [IsERPUser]
    filterset_fields = ['status', 'customer', 'scheduled_delivery_date']

    def create(self, request, *args, **kwargs):
        """
        Supports creating multiple orders in one request.
        """
        is_many = isinstance(request.data, list)
        if not is_many:
            return super().create(request, *args, **kwargs)
        
        serializer = self.get_serializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['patch', 'put'])
    def bulk_update(self, request):
        """
        Updates multiple orders at once. Each must have an 'id'.
        """
        data = request.data
        if not isinstance(data, list):
            return Response({"detail": "Expected a list."}, status=status.HTTP_400_BAD_REQUEST)

        updated = []
        for item in data:
            order_id = item.get('id')
            if not order_id: continue
            try:
                instance = Order.objects.get(id=order_id)
                serializer = self.get_serializer(instance, data=item, partial=True)
                serializer.is_valid(raise_exception=True)
                serializer.save()
                updated.append(serializer.data)
            except Order.DoesNotExist:
                continue
        return Response(updated, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='mark-delivered')
    def mark_delivered(self, request, pk=None):
        order = self.get_object()
        bottles_returned = int(request.data.get('bottles_returned', 0))
        pod_image = request.FILES.get('pod_image')
        
        # Check if POD is required for this tenant
        from administration.models import AdminConfiguration
        config = AdminConfiguration.get_solo()
        if config.enable_delivery_photo and not pod_image:
            return Response(
                {'detail': 'Proof of Delivery (photo) is required by your administrator.'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        from django.db import transaction
        from django.utils import timezone
        with transaction.atomic():
            order.status = OrderStatus.DELIVERED
            order.delivered_at = timezone.now()
            if pod_image:
                order.pod_image = pod_image
            order.save(update_fields=['status', 'delivered_at', 'pod_image'])
            
            from inventory.services import record_bottle_transaction
            from inventory.models import BottleTransactionType
            for item in order.items.all():
                if item.product.is_returnable and item.product.bottle_type:
                    record_bottle_transaction(
                        bottle_type=item.product.bottle_type,
                        quantity=item.quantity,
                        transaction_type=BottleTransactionType.ISSUED,
                        customer=order.customer,
                        order=order,
                        user=request.user if not request.user.is_anonymous else None
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
                        user=request.user if not request.user.is_anonymous else None
                    )
        
        return Response(OrderSerializer(order).data)

    @action(detail=False, methods=['post'], url_path='mark-all-delivered')
    def mark_all_delivered(self, request):
        orders = Order.objects.exclude(status__in=[OrderStatus.DELIVERED, OrderStatus.CANCELLED])
        count = orders.update(status=OrderStatus.DELIVERED)
        return Response({'detail': f'Marked {count} orders as delivered.'})


class RouteViewSet(viewsets.ModelViewSet):
    queryset = Route.objects.all().prefetch_related('stops__order__customer')
    serializer_class = RouteSerializer
    permission_classes = [IsERPUser]

    @action(detail=False, methods=['post'], url_path='create-optimized')
    def create_optimized(self, request):
        name = request.data.get('name')
        date = request.data.get('date')
        order_ids = request.data.get('order_ids', [])
        driver_id = request.data.get('driver_id')
        
        if not all([name, date, order_ids]):
            return Response({'detail': 'name, date, and order_ids are required.'}, status=400)
            
        from accounts.models import User
        driver = User.objects.filter(id=driver_id).first() if driver_id else None
        
        route = create_optimized_route(name, driver, date, order_ids)
        return Response(RouteSerializer(route).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='geojson')
    def geojson(self, request, pk=None):
        route = self.get_object()
        features = []

        if route.geometry:
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[p[0], p[1]] for p in route.geometry.coords]
                },
                "properties": {
                    "type": "route_path",
                    "name": route.name,
                    "distance_km": float(route.total_distance_km)
                }
            })

        for stop in route.stops.all():
            loc = stop.order.customer.location
            if loc:
                features.append({
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [loc.x, loc.y]
                    },
                    "properties": {
                        "type": "stop",
                        "sequence": stop.sequence_number,
                        "customer": stop.order.customer.name,
                        "address": stop.order.delivery_address,
                        "order_id": str(stop.order.id),
                        "status": stop.order.status
                    }
                })

        return Response({
            "type": "FeatureCollection",
            "features": features
        })


class DriverViewSet(viewsets.ViewSet):
    """
    Dedicated endpoints for the Driver Mobile App.
    """
    permission_classes = [IsAuthenticated]

    def retrieve(self, request, pk=None):
        return Response({"detail": "Use specific actions like start-trip"})

    @action(detail=False, methods=['get'], url_path='my-route')
    def my_route(self, request):
        """
        Returns the active route for the logged-in driver for today.
        """
        import datetime
        today = datetime.date.today()
        
        route = Route.objects.filter(
            driver=request.user,
            delivery_date=today,
            is_completed=False
        ).prefetch_related('stops__order__customer').first()
        
        if not route:
            return Response({'detail': 'No active route found for today.'}, status=404)
            
        return Response(RouteSerializer(route).data)

    @action(detail=True, methods=['post'], url_path='start-trip')
    def start_trip(self, request, pk=None):
        """
        Starts the route and marks all orders as IN_TRANSIT.
        pk is the Route ID.
        """
        from django.utils import timezone
        # Professional Error Handling: Distinguish between "Not Found" and "Forbidden"
        route = Route.objects.filter(id=pk).first()
        if not route:
            return Response({'error': f'Route with ID {pk} does not exist in this city.'}, status=status.HTTP_404_NOT_FOUND)
        
        if route.driver != request.user:
            return Response({
                'error': 'Access Denied',
                'detail': f'This route is assigned to {route.driver.username if route.driver else "nobody"}. You (User {request.user.id}) cannot complete it.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        route.started_at = timezone.now()
        route.save(update_fields=['started_at'])
        
        # Update all orders in this route to IN_TRANSIT
        for stop in route.stops.all():
            stop.order.status = OrderStatus.IN_TRANSIT
            stop.order.save(update_fields=['status'])
            
        return Response({'detail': 'Trip started successfully.', 'started_at': route.started_at})

    @action(detail=True, methods=['post'], url_path='complete-trip')
    def complete_trip(self, request, pk=None):
        """
        Finishes the route.
        pk is the Route ID.
        """
        from django.utils import timezone
        # Professional Error Handling: Distinguish between "Not Found" and "Forbidden"
        route = Route.objects.filter(id=pk).first()
        if not route:
            return Response({'error': f'Route with ID {pk} does not exist in this city.'}, status=status.HTTP_404_NOT_FOUND)
        
        if route.driver != request.user:
            return Response({
                'error': 'Access Denied',
                'detail': f'This route is assigned to {route.driver.username if route.driver else "nobody"}. You (User {request.user.id}) cannot complete it.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        route.completed_at = timezone.now()
        route.is_completed = True
        route.save(update_fields=['completed_at', 'is_completed'])
            
        return Response({'detail': 'Trip completed successfully.', 'completed_at': route.completed_at})

    @action(detail=True, methods=['post'], url_path='submit-delivery')
    def submit_delivery(self, request, pk=None):
        """
        One-tap delivery submission for the driver.
        pk is the Order ID.
        """
        # Logic is similar to OrderViewSet.mark_delivered but optimized for driver context
        order_viewset = OrderViewSet()
        order_viewset.request = request
        order_viewset.kwargs = {'pk': pk}
        return order_viewset.mark_delivered(request, pk=pk)
