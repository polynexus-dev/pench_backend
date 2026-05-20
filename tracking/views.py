from rest_framework import viewsets, serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from django.contrib.gis.geos import LineString
from core.permissions import IsERPUser
from .models import DriverLocation, DriverTrail
import datetime


class DriverLocationSerializer(serializers.ModelSerializer):
    driver_name = serializers.CharField(source='user.get_full_name', read_only=True)
    lat = serializers.FloatField(source='location.y', read_only=True)
    lng = serializers.FloatField(source='location.x', read_only=True)
    trail = serializers.SerializerMethodField()
    distance_km = serializers.SerializerMethodField()
    planned_route = serializers.SerializerMethodField()
    delivery_status_summary = serializers.SerializerMethodField()
    deliveries = serializers.SerializerMethodField()

    class Meta:
        model = DriverLocation
        fields = [
            'id', 'user', 'driver_name', 'lat', 'lng', 'trail', 
            'distance_km', 'planned_route', 'delivery_status_summary', 
            'deliveries', 'updated_at'
        ]

    def get_trail(self, obj):
        from routing.models import Route, RouteStatus
        active_route = Route.objects.filter(
            driver__user_id=obj.user.id,
            status=RouteStatus.IN_PROGRESS
        ).first()
        
        if active_route:
            trails = DriverTrail.objects.filter(
                user=obj.user,
                route=active_route
            ).order_by('timestamp')
        else:
            import datetime
            today = datetime.date.today()
            trails = DriverTrail.objects.filter(
                user=obj.user,
                route__isnull=True,
                timestamp__date=today
            ).order_by('timestamp')
        
        # Robust coordinates coordinate extraction for GIS / non-GIS setups
        def get_coords(t):
            loc = t.cleaned_location or t.location
            if hasattr(loc, 'x'): return [loc.x, loc.y]
            if isinstance(loc, dict): return [loc.get('lng'), loc.get('lat')]
            return [0, 0]
            
        return [get_coords(t) for t in trails]

    def get_distance_km(self, obj):
        trail_coords = self.get_trail(obj)
        if not trail_coords or len(trail_coords) < 2:
            return 0.0
        
        import math
        def calc_dist(lon1, lat1, lon2, lat2):
            lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])
            dlon = lon2 - lon1 
            dlat = lat2 - lat1 
            a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
            c = 2 * math.asin(math.sqrt(a)) 
            return c * 6371000

        total_dist = 0.0
        for i in range(len(trail_coords) - 1):
            total_dist += calc_dist(
                trail_coords[i][0], trail_coords[i][1],
                trail_coords[i+1][0], trail_coords[i+1][1]
            )
        return round(total_dist / 1000.0, 2)

    def get_planned_route(self, obj):
        from routing.models import Route, RouteStatus
        active_route = Route.objects.filter(
            driver__user_id=obj.user.id,
            status=RouteStatus.IN_PROGRESS
        ).first()
        
        if not active_route or not active_route.geometry:
            return []
            
        geom = active_route.geometry
        if hasattr(geom, 'coords'):
            return list(geom.coords)
        elif isinstance(geom, str):
            try:
                import json
                parsed = json.loads(geom)
                if isinstance(parsed, dict) and 'coordinates' in parsed:
                    return parsed['coordinates']
            except Exception:
                pass
            try:
                pts = []
                for part in geom.replace('LINESTRING', '').replace('(', '').replace(')', '').strip().split(','):
                    coord = part.strip().split()
                    if len(coord) >= 2:
                        pts.append([float(coord[0]), float(coord[1])])
                return pts
            except Exception:
                pass
        return []

    def _get_active_route_orders(self, obj):
        from routing.models import Route, RouteStatus
        active_route = Route.objects.filter(
            driver__user_id=obj.user.id,
            status=RouteStatus.IN_PROGRESS
        ).first()
        if active_route:
            return active_route.orders.all().select_related('customer')
        return []

    def get_delivery_status_summary(self, obj):
        orders = self._get_active_route_orders(obj)
        if not orders:
            return None
        
        summary = {
            "total": len(orders),
            "pending": 0,
            "delivered": 0,
            "undelivered": 0,
            "other": 0
        }
        for order in orders:
            status = order.status.lower()
            if status in ['pending', 'confirmed', 'dispatched', 'in_transit']:
                summary["pending"] += 1
            elif status == 'delivered':
                summary["delivered"] += 1
            elif status == 'undelivered':
                summary["undelivered"] += 1
            else:
                summary["other"] += 1
        return summary

    def get_deliveries(self, obj):
        orders = self._get_active_route_orders(obj)
        if not orders:
            return []
            
        result = []
        for order in orders:
            loc = order.customer.location
            lat, lng = 0.0, 0.0
            if loc:
                if hasattr(loc, 'y') and hasattr(loc, 'x'):
                    lat, lng = float(loc.y), float(loc.x)
                elif isinstance(loc, dict):
                    lat = float(loc.get('lat') or 0.0)
                    lng = float(loc.get('lng') or 0.0)
            
            result.append({
                "order_id": order.id,
                "customer_name": order.customer.name,
                "address": order.delivery_address,
                "lat": lat,
                "lng": lng,
                "status": order.status,
                "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None
            })
        return result


class DriverLocationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API for Admins to see the live location of all drivers.
    """
    queryset = DriverLocation.objects.all().select_related('user')
    serializer_class = DriverLocationSerializer
    permission_classes = [IsERPUser]

    @action(detail=True, methods=['get'])
    def trail(self, request, pk=None):
        """
        Returns the historical trail of a driver as GeoJSON LineString.
        Supports filtering by `route_id`, active route, or `date`.
        """
        location_obj = self.get_object()
        driver = location_obj.user
        
        route_id = request.query_params.get('route_id')
        date_str = request.query_params.get('date')
        route_info = ""
        route_obj = None
        
        if route_id:
            from routing.models import Route
            route_obj = Route.objects.filter(id=route_id).first()
            trails = DriverTrail.objects.filter(
                user=driver,
                route_id=route_id
            ).order_by('timestamp')
            route_info = f"Route #{route_id}"
        elif not date_str:
            # Default: try to fetch the current active route's trail first
            from routing.models import Route, RouteStatus
            active_route = Route.objects.filter(
                driver__user_id=driver.id,
                status=RouteStatus.IN_PROGRESS
            ).first()
            route_obj = active_route
            if active_route:
                trails = DriverTrail.objects.filter(
                    user=driver,
                    route=active_route
                ).order_by('timestamp')
                route_info = f"Active Route #{active_route.id}"
            else:
                # Fall back to today's date-based trail (route-less)
                date = datetime.date.today()
                trails = DriverTrail.objects.filter(
                    user=driver,
                    timestamp__date=date
                ).order_by('timestamp')
                route_info = f"Date: {date}"
        else:
            date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
            trails = DriverTrail.objects.filter(
                user=driver,
                timestamp__date=date
            ).order_by('timestamp')
            route_info = f"Date: {date}"

        if not trails.exists():
            return Response({
                "type": "Feature",
                "geometry": None,
                "properties": {"message": "No trail found.", "info": route_info}
            })

        # Planned route coordinates extraction
        planned_coords = []
        if route_obj and route_obj.geometry:
            geom = route_obj.geometry
            if hasattr(geom, 'coords'):
                planned_coords = list(geom.coords)
            elif isinstance(geom, str):
                try:
                    import json
                    parsed = json.loads(geom)
                    if isinstance(parsed, dict) and 'coordinates' in parsed:
                        planned_coords = parsed['coordinates']
                except Exception:
                    pass
                if not planned_coords:
                    try:
                        pts = []
                        for part in geom.replace('LINESTRING', '').replace('(', '').replace(')', '').strip().split(','):
                            coord = part.strip().split()
                            if len(coord) >= 2:
                                pts.append([float(coord[0]), float(coord[1])])
                        planned_coords = pts
                    except Exception:
                        pass

        # Extract delivery status summary and list of deliveries for the trail
        delivery_status_summary = None
        deliveries = []
        if route_obj:
            orders = route_obj.orders.all().select_related('customer')
            if orders:
                summary = {
                    "total": len(orders),
                    "pending": 0,
                    "delivered": 0,
                    "undelivered": 0,
                    "other": 0
                }
                for order in orders:
                    status = order.status.lower()
                    if status in ['pending', 'confirmed', 'dispatched', 'in_transit']:
                        summary["pending"] += 1
                    elif status == 'delivered':
                        summary["delivered"] += 1
                    elif status == 'undelivered':
                        summary["undelivered"] += 1
                    else:
                        summary["other"] += 1
                    
                    loc = order.customer.location
                    lat, lng = 0.0, 0.0
                    if loc:
                        if hasattr(loc, 'y') and hasattr(loc, 'x'):
                            lat, lng = float(loc.y), float(loc.x)
                        elif isinstance(loc, dict):
                            lat = float(loc.get('lat') or 0.0)
                            lng = float(loc.get('lng') or 0.0)
                            
                    deliveries.append({
                        "order_id": order.id,
                        "customer_name": order.customer.name,
                        "address": order.delivery_address,
                        "lat": lat,
                        "lng": lng,
                        "status": order.status,
                        "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None
                    })
                delivery_status_summary = summary

        # Build coordinates using pre-cleaned data from DB
        coords = []
        for t in trails:
            loc = t.cleaned_location or t.location
            if hasattr(loc, 'x'):
                coords.append([loc.x, loc.y])
            elif isinstance(loc, dict):
                coords.append([loc.get('lng'), loc.get('lat')])

        if not coords:
            return Response({
                "type": "Feature",
                "geometry": None,
                "properties": {"message": "No coordinates extracted.", "info": route_info}
            })

        # Generate continuous curved road geometry using OSRM Match API for high-fidelity alignment
        from routing.services.osrm_client import match_trail
        
        # OSRM has a limit on waypoints in the URL (usually 100)
        # Downsample coordinates if there are too many, OSRM will match between them anyway
        if len(coords) > 90:
            step = len(coords) // 90 + 1
            sampled_coords = coords[::step]
            if sampled_coords[-1] != coords[-1]:
                sampled_coords.append(coords[-1])
        else:
            sampled_coords = coords
            
        route_coords = match_trail(sampled_coords) if len(sampled_coords) > 1 else coords
        
        # Calculate final snapped distance
        import math
        def calc_dist(lon1, lat1, lon2, lat2):
            lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])
            dlon = lon2 - lon1 
            dlat = lat2 - lat1 
            a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
            c = 2 * math.asin(math.sqrt(a)) 
            return c * 6371000

        total_dist = 0.0
        for i in range(len(route_coords) - 1):
            total_dist += calc_dist(
                route_coords[i][0], route_coords[i][1],
                route_coords[i+1][0], route_coords[i+1][1]
            )
        distance_km = round(total_dist / 1000.0, 2)

        # If only one point, we can't make a LineString, return a Point
        if len(route_coords) < 2:
            geometry = {
                "type": "Point",
                "coordinates": route_coords[0] if route_coords else [0,0]
            }
        else:
            geometry = {
                "type": "LineString",
                "coordinates": route_coords
            }

        return Response({
            "type": "Feature",
            "geometry": geometry,
            "properties": {
                "driver_id": driver.id,
                "driver_name": driver.get_full_name(),
                "info": route_info,
                "point_count": len(coords),
                "distance_km": distance_km,
                "planned_route": planned_coords,
                "delivery_status_summary": delivery_status_summary,
                "deliveries": deliveries
            }
        })
