import json
import traceback
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
try:
    from django.contrib.gis.geos import Point
except ImportError:
    Point = None
from django_tenants.utils import schema_context
from .models import DriverLocation, DriverTrail, HAS_GIS


import math

def calculate_distance(lon1, lat1, lon2, lat2):
    """
    Calculate the great circle distance between two points 
    on the earth (specified in decimal degrees) in meters.
    """
    lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1 
    dlat = lat2 - lat1 
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a)) 
    r = 6371000  # Radius of earth in meters
    return c * r

def calculate_trail_distance(coords):
    """
    Calculate the total cumulative distance along a list of [lng, lat] coordinates in kilometers.
    """
    if not coords or len(coords) < 2:
        return 0.0
    
    total_dist = 0.0
    for i in range(len(coords) - 1):
        total_dist += calculate_distance(
            coords[i][0], coords[i][1],
            coords[i+1][0], coords[i+1][1]
        )
    return round(total_dist / 1000.0, 2)


class TrackingConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        self.tenant = self.scope.get("tenant")
        
        print(f"[WS Connect] User: {self.user}, Tenant: {self.tenant}")
        
        if self.user.is_anonymous or not self.tenant:
            print("[WS Connect] REJECTED: Anonymous or No Tenant")
            await self.close()
            return
 
        if self.user.is_staff:
            await self.channel_layer.group_add("admins", self.channel_name)
        
        await self.accept()
        print("[WS Connect] ACCEPTED")
 
        if self.user.is_staff:
            initial_state = await self.get_initial_state()
            await self.send(text_data=json.dumps({
                "type": "initial_state",
                "drivers": initial_state
            }))
 
    async def disconnect(self, close_code):
        if hasattr(self, 'user') and self.user.is_staff:
            await self.channel_layer.group_discard("admins", self.channel_name)
 
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            lat = data.get('lat')
            lng = data.get('lng')
 
            if lat and lng:
                print(f"[WS Receive] Driver {self.user.username}: Lat={lat}, Lng={lng}")
                # Update Database and get full trail + distance + planned route coordinates
                trail_points, distance_km, planned_route = await self.update_driver_location(lat, lng)
                
                # If safeguard triggered (ghost simulator), abort broadcast
                if trail_points is None:
                    return
 
                # Broadcast to Admins
                await self.channel_layer.group_send(
                    "admins",
                    {
                        "type": "broadcast_location",
                        "driver_id": str(self.user.id),
                        "driver_name": self.user.get_full_name(),
                        "lat": lat,
                        "lng": lng,
                        "trail": trail_points, # Snapped historical trail array of [lng, lat]
                        "distance_km": distance_km, # Distance traveled in KM
                        "planned_route": planned_route # Original planned road map coordinates
                    }
                )
 
                # Also send back to the sender (direct acknowledgment with trail)
                await self.send(text_data=json.dumps({
                    "type": "location_update_response",
                    "driver_id": str(self.user.id),
                    "lat": lat,
                    "lng": lng,
                    "trail": trail_points,
                    "distance_km": distance_km,
                    "planned_route": planned_route
                }))
        except Exception as e:
            print(f"[WS Receive Error] CRASH: {str(e)}")
            traceback.print_exc()
 
    async def broadcast_location(self, event):
        await self.send(text_data=json.dumps(event))
 
    def get_current_trail(self, user_id, active_route):
        """
        Helper method to retrieve the continuous road-aligned trail for a driver.
        Filters strictly by the active route if present; otherwise falls back
        to the last 12 hours of route-less (idle) breadcrumbs.
        """
        if active_route:
            historical_trails = DriverTrail.objects.filter(
                user_id=user_id,
                route=active_route
            ).order_by('timestamp')
        else:
            from django.utils import timezone
            from datetime import timedelta
            time_threshold = timezone.now() - timedelta(hours=12)
            historical_trails = DriverTrail.objects.filter(
                user_id=user_id,
                route__isnull=True,
                timestamp__gte=time_threshold
            ).order_by('timestamp')
            
        def get_cleaned_coords(t):
            loc = t.cleaned_location or t.location
            if hasattr(loc, 'x'): return [loc.x, loc.y]
            if isinstance(loc, dict): return [loc.get('lng'), loc.get('lat')]
            return [0, 0]

        snapped_coords = [get_cleaned_coords(t) for t in historical_trails]
        
        # Filter out consecutive duplicates to prevent redundant OSRM routing calls
        unique_coords = []
        for coord in snapped_coords:
            if not unique_coords or unique_coords[-1] != coord:
                unique_coords.append(coord)
                
        if len(unique_coords) >= 2:
            # Use match_trail for high-fidelity road alignment to avoid straight jumps or routing loops
            from routing.services.osrm_client import match_trail
            return match_trail(unique_coords)
        else:
            return unique_coords

    @database_sync_to_async
    def update_driver_location(self, lat, lng):
        try:
            if not self.tenant or self.tenant.schema_name == 'public':
                return None
 
            with schema_context(self.tenant.schema_name):
                p_lng = float(lng)
                p_lat = float(lat)
                
                # 1. Snap the raw point immediately to the nearest road
                from routing.services.osrm_client import snap_to_road
                snapped_lng, snapped_lat = snap_to_road(p_lng, p_lat)
                
                if HAS_GIS and Point:
                    location_data = Point(p_lng, p_lat, srid=4326)
                    cleaned_location_data = Point(snapped_lng, snapped_lat, srid=4326)
                else:
                    location_data = {'lat': p_lat, 'lng': p_lng}
                    cleaned_location_data = {'lat': snapped_lat, 'lng': snapped_lng}
                
                # Retrieve the active route for this driver
                from routing.models import Route, RouteStatus
                active_route = Route.objects.filter(
                    driver__user_id=self.user.id,
                    status=RouteStatus.IN_PROGRESS
                ).first()
                
                # Planned route coordinates extraction
                planned_coords = []
                if active_route and active_route.geometry:
                    geom = active_route.geometry
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
                
                # Check for GPS Jitter / Movement Filter (8 meters threshold)
                prev_trail = DriverTrail.objects.filter(
                    user_id=self.user.id,
                    route=active_route
                ).order_by('-timestamp').first()
                
                if prev_trail:
                    loc = prev_trail.location
                    if hasattr(loc, 'x'):
                        prev_lng, prev_lat = loc.x, loc.y
                    elif isinstance(loc, dict):
                        prev_lng, prev_lat = loc.get('lng'), loc.get('lat')
                    else:
                        prev_lng, prev_lat = None, None
                        
                    if prev_lng is not None and prev_lat is not None:
                        dist = calculate_distance(p_lng, p_lat, prev_lng, prev_lat)
                        if dist < 8.0:
                            # STATIONARY GPS JITTER: Driver has not moved significantly.
                            # Skip creating a new DriverTrail point, but update live position.
                            DriverLocation.objects.update_or_create(
                                user_id=self.user.id,
                                defaults={'location': cleaned_location_data}
                            )
                            current_trail = self.get_current_trail(self.user.id, active_route)
                            return current_trail, calculate_trail_distance(current_trail), planned_coords
                
                # 2. Update current live position (using snapped location for precision)
                DriverLocation.objects.update_or_create(
                    user_id=self.user.id,
                    defaults={'location': cleaned_location_data}
                )
                
                # 3. Create the new trail record (tagged with active_route)
                DriverTrail.objects.create(
                    user_id=self.user.id,
                    route=active_route,
                    location=location_data,
                    cleaned_location=cleaned_location_data
                )
 
                # 4. Fetch the clean snapping-routed trail and calculate cumulative distance
                current_trail = self.get_current_trail(self.user.id, active_route)
                return current_trail, calculate_trail_distance(current_trail), planned_coords
 
        except Exception as e:
            print(f"[DB Sync Error] {str(e)}")
            traceback.print_exc()
            return [], 0.0, []
 
    @database_sync_to_async
    def get_initial_state(self):
        try:
            if not self.tenant or self.tenant.schema_name == 'public':
                return []
 
            with schema_context(self.tenant.schema_name):
                from django.utils import timezone
                from datetime import timedelta
                
                time_threshold = timezone.now() - timedelta(hours=12)
                
                # Fetch all active driver locations updated in the last 12 hours
                active_locations = DriverLocation.objects.select_related('user').filter(
                    updated_at__gte=time_threshold
                )
                
                drivers_state = []
                for loc in active_locations:
                    driver = loc.user
                    
                    # Get active route
                    from routing.models import Route, RouteStatus
                    active_route = Route.objects.filter(
                        driver__user_id=driver.id,
                        status=RouteStatus.IN_PROGRESS
                    ).first()
                    
                    # Fetch their clean snapping-routed trail
                    trail_points = self.get_current_trail(driver.id, active_route)
                    distance_km = calculate_trail_distance(trail_points)
                    
                    # Planned route coordinates extraction
                    planned_coords = []
                    if active_route and active_route.geometry:
                        geom = active_route.geometry
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
                    
                    # Snapped lat/lng of current position
                    current_lat = loc.location.y if hasattr(loc.location, 'y') else loc.location.get('lat')
                    current_lng = loc.location.x if hasattr(loc.location, 'x') else loc.location.get('lng')
                    
                    drivers_state.append({
                        "driver_id": str(driver.id),
                        "driver_name": driver.get_full_name() or driver.username,
                        "lat": current_lat,
                        "lng": current_lng,
                        "trail": trail_points,
                        "distance_km": distance_km,
                        "planned_route": planned_coords
                    })
                return drivers_state
        except Exception as e:
            print(f"[Initial State Error] {str(e)}")
            traceback.print_exc()
            return []
