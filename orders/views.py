from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from core.permissions import IsERPUser, HasGroupPermission
from .models import Order, OrderStatus, Route
from .serializers import OrderSerializer, RouteSerializer
from .services import create_optimized_route
import datetime


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.select_related('customer__zone__assigned_driver', 'route_stop__route__driver').prefetch_related('items')
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated] # Base permission is just authenticated
    filterset_fields = ['status', 'customer', 'scheduled_delivery_date']

    def get_permissions(self):
        """
        ERP users can do everything. Customers can only list and retrieve.
        """
        if self.action in ['list', 'retrieve']:
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
        if hasattr(user, 'customer_profile'):
            return qs.filter(customer=user.customer_profile)
            
        # Allow drivers to access orders assigned to their routes
        from .models import RouteStop
        assigned_order_ids = RouteStop.objects.filter(route__driver=user).values_list('order_id', flat=True)
        if assigned_order_ids.exists() or getattr(user, 'is_driver', False):
            return qs.filter(id__in=assigned_order_ids)
            
        # Fallback for other roles: no orders unless they are ERP users
        return qs.none()

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

    @action(detail=False, methods=['post'], url_path='sync')
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
                assigned_zone = Zone.objects.filter(boundary__contains=loc, is_active=True).first()
            else:
                coords = _parse_coordinates(loc)
                if coords:
                    lng, lat = coords
                    for zone in zones_list:
                        if zone.boundary:
                            poly_coords = None
                            if isinstance(zone.boundary, dict):
                                geom_type = zone.boundary.get('type')
                                if geom_type == 'Polygon':
                                    poly_coords = zone.boundary.get('coordinates')
                                elif geom_type == 'MultiPolygon':
                                    for sub_poly in zone.boundary.get('coordinates', []):
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
                customer.save(update_fields=['zone'])
                zone_updated += 1

        # ---------- STEP 2: Re-assign pending orders to zone drivers ----------
        date_str = request.data.get('date') or dt.date.today().isoformat()

        pending_orders = Order.objects.filter(
            scheduled_delivery_date=date_str,
            status__in=[OrderStatus.PENDING, OrderStatus.CONFIRMED],
            customer__zone__isnull=False,
        ).select_related('customer__zone', 'customer__zone__assigned_driver')

        # Group orders by zone
        zone_orders = {}
        for order in pending_orders:
            zone = order.customer.zone
            if zone:
                zone_orders.setdefault(zone, []).append(order)

        routes_created = 0
        route_errors = []
        for zone, z_orders in zone_orders.items():
            driver = zone.assigned_driver
            if not driver:
                route_errors.append({
                    'zone': zone.name,
                    'error': 'No primary driver assigned.'
                })
                continue

            order_ids = [str(o.id) for o in z_orders]
            route_name = f"{zone.name} - {date_str}"

            try:
                create_optimized_route(route_name, driver, date_str, order_ids)
                routes_created += 1
            except Exception as e:
                route_errors.append({
                    'zone': zone.name,
                    'error': str(e)
                })

        # ---------- STEP 3: Return refreshed order list ----------
        qs = self.get_queryset()
        serializer = self.get_serializer(qs, many=True)

        return Response({
            'orders': serializer.data,
            'sync_summary': {
                'customers_zone_updated': zone_updated,
                'routes_created': routes_created,
                'route_errors': route_errors,
            }
        }, status=status.HTTP_200_OK)

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
        bottles_issued = request.data.get('bottles_issued')
        if bottles_issued is not None:
            try:
                bottles_issued = int(bottles_issued)
            except (ValueError, TypeError):
                bottles_issued = None
                
        pod_image = request.FILES.get('pod_image')
        pod_lat = request.data.get('pod_latitude')
        pod_lon = request.data.get('pod_longitude')
        
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
            if pod_lat:
                order.pod_latitude = pod_lat
            if pod_lon:
                order.pod_longitude = pod_lon
            order.save(update_fields=['status', 'delivered_at', 'pod_image', 'pod_latitude', 'pod_longitude'])
            
            from inventory.services import record_bottle_transaction
            from inventory.models import BottleTransactionType
            for item in order.items.all():
                if item.product.is_returnable and item.product.bottle_type:
                    qty = bottles_issued if bottles_issued is not None else item.quantity
                    record_bottle_transaction(
                        bottle_type=item.product.bottle_type,
                        quantity=qty,
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

    @action(detail=True, methods=['post'], url_path='mark-undelivered')
    def mark_undelivered(self, request, pk=None):
        order = self.get_object()
        pod_image = request.FILES.get('pod_image')
        pod_lat = request.data.get('pod_latitude')
        pod_lon = request.data.get('pod_longitude')
        
        if not pod_image:
            return Response(
                {'detail': 'Proof of Attempt (photo) is required to mark an order as undelivered.'}, 
                status=status.HTTP_400_BAD_REQUEST
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
            order.save(update_fields=['status', 'delivered_at', 'pod_image', 'pod_latitude', 'pod_longitude'])
            
        return Response(OrderSerializer(order).data)

    @action(detail=False, methods=['post'], url_path='mark-all-delivered')
    def mark_all_delivered(self, request):
        orders = Order.objects.exclude(status__in=[OrderStatus.DELIVERED, OrderStatus.CANCELLED, OrderStatus.UNDELIVERED])
        count = orders.update(status=OrderStatus.DELIVERED)
        return Response({'detail': f'Marked {count} orders as delivered.'})


class RouteViewSet(viewsets.ModelViewSet):
    queryset = Route.objects.all().prefetch_related('stops__order__customer')
    serializer_class = RouteSerializer
    permission_classes = [IsERPUser, HasGroupPermission]
    required_groups = ['Logistics_Managers', 'ERP_Admins']
    filterset_fields = ['delivery_date', 'driver', 'is_completed']

    @action(detail=False, methods=['post'], url_path='create-optimized')
    def create_optimized(self, request):
        name = request.data.get('name')
        # Support both 'date' and 'delivery_date'
        date = request.data.get('date') or request.data.get('delivery_date')
        order_ids = request.data.get('order_ids', [])
        driver_id = request.data.get('driver_id')
        zone_id = request.data.get('zone')

        # If a zone is provided, resolve order_ids, name, and driver automatically
        if zone_id:
            from routing.models import Zone
            zone = Zone.objects.filter(id=zone_id).first()
            if not zone:
                return Response({'detail': f"Zone with ID {zone_id} not found."}, status=status.HTTP_404_NOT_FOUND)
            
            # Fetch all pending or confirmed orders for this zone and date
            orders = Order.objects.filter(
                customer__zone_id=zone_id,
                scheduled_delivery_date=date,
                status__in=[OrderStatus.PENDING, OrderStatus.CONFIRMED]
            )
            
            if not orders.exists():
                return Response({
                    'detail': f"No pending or confirmed orders found in zone '{zone.name}' for date {date}."
                }, status=status.HTTP_400_BAD_REQUEST)
                
            order_ids = list(orders.values_list('id', flat=True))
            if not name:
                name = f"{zone.name} - {date}"
            if not driver_id and zone.assigned_driver:
                driver_id = zone.assigned_driver.id
        
        # Validation with descriptive errors
        missing_fields = []
        if not name: missing_fields.append('name')
        if not date: missing_fields.append('date/delivery_date')
        if not order_ids: missing_fields.append('order_ids')
        
        if missing_fields:
            return Response({
                'detail': f"Missing required fields: {', '.join(missing_fields)}",
                'received_data': request.data
            }, status=status.HTTP_400_BAD_REQUEST)
            
        from accounts.models import User
        driver = User.objects.filter(id=driver_id).first() if driver_id else None
        
        route = create_optimized_route(name, driver, date, order_ids)
        
        # Return the route with extra debug info to help troubleshoot empty stops
        response_data = RouteSerializer(route).data
        response_data['debug'] = {
            'requested_order_ids_count': len(order_ids),
            'orders_found_in_db': Order.objects.filter(id__in=order_ids).count(),
            'valid_orders_with_locations': Order.objects.filter(id__in=order_ids).exclude(customer__location__isnull=True).count(),
        }
        return Response(response_data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='assign-pending')
    def assign_pending(self, request):
        """
        Bulk-assigns pending orders of customers to their primary zone drivers and creates optimized routes.
        """
        date = request.data.get('date') or request.data.get('delivery_date')
        if not date:
            import datetime
            date = datetime.date.today().isoformat()
            
        from routing.models import Zone
        from orders.services import create_optimized_route
        
        # Fetch pending or confirmed orders for this date that are in a zone
        orders = Order.objects.filter(
            scheduled_delivery_date=date,
            status__in=[OrderStatus.PENDING, OrderStatus.CONFIRMED],
            customer__zone__isnull=False
        ).select_related('customer__zone', 'customer__zone__assigned_driver')
        
        # Group by zone
        zone_orders = {}
        for order in orders:
            zone = order.customer.zone
            if zone:
                zone_orders.setdefault(zone, []).append(order)
                
        created_routes = []
        errors = []
        
        for zone, z_orders in zone_orders.items():
            driver = zone.assigned_driver
            if not driver:
                errors.append({
                    'zone_id': str(zone.id),
                    'zone_name': zone.name,
                    'error': 'No primary driver assigned to this zone.'
                })
                continue
                
            order_ids = [str(o.id) for o in z_orders]
            name = f"{zone.name} - {date}"
            
            try:
                route = create_optimized_route(name, driver, date, order_ids)
                created_routes.append(RouteSerializer(route).data)
            except Exception as e:
                errors.append({
                    'zone_id': str(zone.id),
                    'zone_name': zone.name,
                    'error': str(e)
                })
                
        return Response({
            'date': date,
            'total_zones_processed': len(zone_orders),
            'created_routes': created_routes,
            'errors': errors
        }, status=status.HTTP_200_OK)

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
    permission_classes = [IsAuthenticated, HasGroupPermission]
    required_groups = ['Drivers', 'Logistics_Managers']

    def retrieve(self, request, pk=None):
        return Response({"detail": "Use specific actions like start-trip"})

    @action(detail=False, methods=['get'], url_path='trip-status')
    def trip_status(self, request):
        """
        Checks if the logged-in driver's trip is started or not.
        Returns the on_trip status and information about the active route.
        """
        from django_tenants.utils import schema_context
        from django.db import connection
        
        user = request.user
        schema = user.tenant_schema
        context_schema = schema if connection.schema_name == 'public' and schema else connection.schema_name
        
        with schema_context(context_schema):
            from routing.models import Driver
            
            driver_profile = Driver.objects.filter(user=user).first()
            on_trip = driver_profile.on_trip if driver_profile else False
            
            # Find any active route (not completed) assigned to the driver
            active_route = Route.objects.filter(
                driver=user,
                is_completed=False
            ).order_by('delivery_date').first()
            
            route_data = None
            if active_route:
                route_data = {
                    'id': str(active_route.id),
                    'name': active_route.name,
                    'delivery_date': active_route.delivery_date,
                    'started_at': active_route.started_at,
                    'is_started': active_route.started_at is not None
                }
                # If they have an active route that has started, they are on a trip
                if active_route.started_at is not None:
                    on_trip = True
                    
            return Response({
                'on_trip': on_trip,
                'active_route': route_data
            })

    @action(detail=False, methods=['get'], url_path='my-route')
    def my_route(self, request):
        """
        Returns the active route for the logged-in driver for today.
        """
        from django_tenants.utils import schema_context
        from django.db import connection
        
        user = request.user
        schema = user.tenant_schema
        
        # If we are in public schema, switch to driver's schema
        context_schema = schema if connection.schema_name == 'public' and schema else connection.schema_name
        
        with schema_context(context_schema):
            # Look for the oldest incomplete active route
            route = Route.objects.filter(
                driver=user,
                is_completed=False
            ).prefetch_related('stops__order__customer').order_by('delivery_date').first()
            
            if not route:
                return Response({'detail': 'No active route found for today.'}, status=404)
                
            return Response(RouteSerializer(route).data)

    @action(detail=False, methods=['post'], url_path='start-tracking',
           permission_classes=[IsAuthenticated])
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

        # Auto-assign user to Drivers group so future driver endpoints also work
        drivers_group, _ = Group.objects.get_or_create(name='Drivers')
        if not user.groups.filter(name='Drivers').exists():
            user.groups.add(drivers_group)

        # Mark user as driver if not already
        if not user.is_driver:
            user.is_driver = True
            user.save(update_fields=['is_driver'])

        schema = user.tenant_schema
        context_schema = schema if connection.schema_name == 'public' and schema else connection.schema_name

        with schema_context(context_schema):
            from routing.models import Driver, Route, RouteStatus

            # Step 1: Ensure a Driver profile exists for this user
            driver_profile, created_profile = Driver.objects.get_or_create(
                user=user,
                defaults={
                    'vehicle_plate': f'TEST-{user.username[:6].upper()}',
                    'vehicle_type': 'van',
                    'is_available': True,
                    'on_trip': False,
                }
            )

            # Step 2: Check if there's already an active/in-progress route today
            today = datetime.date.today()
            existing_route = Route.objects.filter(
                driver=driver_profile,
                is_completed=False,
                delivery_date=today
            ).order_by('-created_at').first()

            if existing_route:
                # Already has a route - just mark it as started if not yet
                if existing_route.status != RouteStatus.IN_PROGRESS:
                    existing_route.status = RouteStatus.IN_PROGRESS
                    existing_route.started_at = timezone.now()
                    existing_route.save(update_fields=['status', 'started_at'])
                driver_profile.is_available = False
                driver_profile.on_trip = True
                driver_profile.save(update_fields=['is_available', 'on_trip'])
                return Response({
                    'detail': 'Tracking session started on existing route.',
                    'route_id': str(existing_route.id),
                    'route_name': existing_route.name,
                    'is_test_route': False,
                    'started_at': existing_route.started_at
                })

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
            driver_profile.save(update_fields=['is_available', 'on_trip'])

            return Response({
                'detail': 'Dummy tracking route created and trip started. Connect WebSocket and send GPS coordinates.',
                'route_id': str(dummy_route.id),
                'route_name': dummy_route.name,
                'is_test_route': True,
                'started_at': dummy_route.started_at,
                'instructions': 'Connect WebSocket: ws://<server>/ws/tracking/?token=<jwt_token> and send {"lat": 21.14, "lng": 79.08}'
            })

    @action(detail=False, methods=['post'], url_path='stop-tracking',
            permission_classes=[IsAuthenticated])
    def stop_tracking(self, request):
        """
        Stops the active GPS tracking session for the driver.
        Marks the active route as completed and frees the driver.
        """
        from django_tenants.utils import schema_context
        from django.db import connection
        from django.utils import timezone
        import datetime

        user = request.user
        schema = user.tenant_schema
        context_schema = schema if connection.schema_name == 'public' and schema else connection.schema_name

        with schema_context(context_schema):
            from routing.models import Driver, Route, RouteStatus

            driver_profile = Driver.objects.filter(user=user).first()
            if not driver_profile:
                return Response({'detail': 'No driver profile found.'}, status=404)

            today = datetime.date.today()
            active_route = Route.objects.filter(
                driver=driver_profile,
                is_completed=False,
                delivery_date=today,
                status=RouteStatus.IN_PROGRESS
            ).order_by('-created_at').first()

            if not active_route:
                return Response({'detail': 'No active tracking session found.'}, status=404)

            active_route.is_completed = True
            active_route.completed_at = timezone.now()
            active_route.status = RouteStatus.COMPLETED
            active_route.save(update_fields=['is_completed', 'completed_at', 'status'])

            driver_profile.is_available = True
            driver_profile.on_trip = False
            driver_profile.save(update_fields=['is_available', 'on_trip'])

            return Response({
                'detail': 'Tracking session stopped.',
                'route_id': str(active_route.id),
                'route_name': active_route.name,
                'is_test_route': getattr(active_route, 'is_test_route', False),
                'completed_at': active_route.completed_at,
            })


    @action(detail=True, methods=['post'], url_path='start-trip')
    def start_trip(self, request, pk=None):
        """
        Starts the route and marks all orders as IN_TRANSIT.
        pk is the Route ID.
        """
        from django.utils import timezone
        from django_tenants.utils import schema_context
        from django.db import connection
        
        user = request.user
        schema = user.tenant_schema
        context_schema = schema if connection.schema_name == 'public' and schema else connection.schema_name
        
        with schema_context(context_schema):
            # Professional Error Handling: Distinguish between "Not Found" and "Forbidden"
            route = Route.objects.filter(id=pk).first()
            if not route:
                return Response({'error': f'Route with ID {pk} does not exist in this city.'}, status=status.HTTP_404_NOT_FOUND)
            
            if route.driver != user:
                return Response({
                    'error': 'Access Denied',
                    'detail': f'This route is assigned to {route.driver.username if route.driver else "nobody"}. You (User {user.id}) cannot complete it.'
                }, status=status.HTTP_403_FORBIDDEN)
            
            route.started_at = timezone.now()
            route.save(update_fields=['started_at'])
            
            # Mark Driver Profile as Unavailable (Busy on trip)
            if route.driver:
                from routing.models import Driver
                driver_profile = Driver.objects.filter(user=route.driver).first()
                if driver_profile:
                    driver_profile.is_available = False
                    driver_profile.on_trip = True
                    driver_profile.save(update_fields=['is_available', 'on_trip'])
            
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
        from django_tenants.utils import schema_context
        from django.db import connection
        
        user = request.user
        schema = user.tenant_schema
        context_schema = schema if connection.schema_name == 'public' and schema else connection.schema_name
        
        with schema_context(context_schema):
            # Professional Error Handling: Distinguish between "Not Found" and "Forbidden"
            route = Route.objects.filter(id=pk).first()
            if not route:
                return Response({'error': f'Route with ID {pk} does not exist in this city.'}, status=status.HTTP_404_NOT_FOUND)
            
            if route.driver != user:
                return Response({
                    'error': 'Access Denied',
                    'detail': f'This route is assigned to {route.driver.username if route.driver else "nobody"}. You (User {user.id}) cannot complete it.'
                }, status=status.HTTP_403_FORBIDDEN)
            
            route.completed_at = timezone.now()
            route.is_completed = True
            route.save(update_fields=['completed_at', 'is_completed'])
    
            # Mark Driver Profile as Available again
            if route.driver:
                from routing.models import Driver
                driver_profile = Driver.objects.filter(user=route.driver).first()
                if driver_profile:
                    driver_profile.is_available = True
                    driver_profile.on_trip = False
                    driver_profile.save(update_fields=['is_available', 'on_trip'])
                
            return Response({'detail': 'Trip completed successfully.', 'completed_at': route.completed_at})

    @action(detail=True, methods=['post'], url_path='submit-delivery')
    def submit_delivery(self, request, pk=None):
        """
        One-tap delivery submission for the driver.
        pk is the Order ID.
        """
        from django_tenants.utils import schema_context
        from django.db import connection
        
        user = request.user
        schema = user.tenant_schema
        context_schema = schema if connection.schema_name == 'public' and schema else connection.schema_name
        
        with schema_context(context_schema):
            # Logic is similar to OrderViewSet.mark_delivered but optimized for driver context
            order_viewset = OrderViewSet()
            order_viewset.request = request
            order_viewset.action = 'submit_delivery'
            order_viewset.get_permissions = lambda: [IsAuthenticated()]
            order_viewset.kwargs = {'pk': pk}
            return order_viewset.mark_delivered(request, pk=pk)

    @action(detail=True, methods=['post'], url_path='submit-undelivered')
    def submit_undelivered(self, request, pk=None):
        """
        Submission for driver to mark order as undelivered (proof of attempt required).
        pk is the Order ID.
        """
        from django_tenants.utils import schema_context
        from django.db import connection
        
        user = request.user
        schema = user.tenant_schema
        context_schema = schema if connection.schema_name == 'public' and schema else connection.schema_name
        
        with schema_context(context_schema):
            order_viewset = OrderViewSet()
            order_viewset.request = request
            order_viewset.action = 'submit_undelivered'
            order_viewset.get_permissions = lambda: [IsAuthenticated()]
            order_viewset.kwargs = {'pk': pk}
            return order_viewset.mark_undelivered(request, pk=pk)

    @action(detail=False, methods=['get'], url_path='resolve-qr/(?P<qr_id>[^/.]+)')
    def resolve_qr(self, request, qr_id=None):
        """
        Fetches customer details and today's pending order by QR Code ID.
        """
        from django_tenants.utils import schema_context
        from django.db import connection
        
        user = request.user
        schema = user.tenant_schema
        context_schema = schema if connection.schema_name == 'public' and schema else connection.schema_name
        
        with schema_context(context_schema):
            from crm.models import Customer
            from crm.serializers import CustomerSerializer
            from inventory.models import CustomerBottleBalance
            
            customer = Customer.objects.filter(qr_code_id=qr_id).first()
            if not customer:
                return Response({'detail': 'Invalid QR Code.'}, status=404)
    
            # Get today's pending order for this customer
            today = datetime.date.today()
            order = Order.objects.filter(
                customer=customer,
                scheduled_delivery_date=today,
                status__in=[OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.DISPATCHED, OrderStatus.IN_TRANSIT]
            ).first()
    
            # Get bottle balances
            balances = CustomerBottleBalance.objects.filter(customer=customer)
            balance_data = [
                {
                    'bottle_type': b.bottle_type.name,
                    'balance': b.balance
                } for b in balances
            ]
    
            return Response({
                'customer': CustomerSerializer(customer).data,
                'order': OrderSerializer(order).data if order else None,
                'bottle_balances': balance_data
            })
