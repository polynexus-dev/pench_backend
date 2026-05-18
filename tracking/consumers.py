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
                # Update Database and get full trail
                trail_points = await self.update_driver_location(lat, lng)
                
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
                        "trail": trail_points # Full array of [lng, lat]
                    }
                )

                # Also send back to the sender (direct acknowledgment with trail)
                await self.send(text_data=json.dumps({
                    "type": "location_update_response",
                    "driver_id": str(self.user.id),
                    "lat": lat,
                    "lng": lng,
                    "trail": trail_points
                }))
        except Exception as e:
            print(f"[WS Receive Error] CRASH: {str(e)}")
            traceback.print_exc()

    async def broadcast_location(self, event):
        await self.send(text_data=json.dumps(event))

    @database_sync_to_async
    def update_driver_location(self, lat, lng):
        try:
            if not self.tenant or self.tenant.schema_name == 'public':
                return None

            with schema_context(self.tenant.schema_name):
                p_lng = float(lng)
                p_lat = float(lat)
                
                if HAS_GIS and Point:
                    location_data = Point(p_lng, p_lat, srid=4326)
                else:
                    location_data = {'lat': p_lat, 'lng': p_lng}
                
                # 1. Snap the raw point immediately to the nearest road
                from routing.services.osrm_client import snap_to_road
                snapped_lng, snapped_lat = snap_to_road(p_lng, p_lat)
                
                if HAS_GIS and Point:
                    location_data = Point(p_lng, p_lat, srid=4326)
                    cleaned_location_data = Point(snapped_lng, snapped_lat, srid=4326)
                else:
                    location_data = {'lat': p_lat, 'lng': p_lng}
                    cleaned_location_data = {'lat': snapped_lat, 'lng': snapped_lng}
                
                # 2. Update current live position (using snapped location for precision)
                DriverLocation.objects.update_or_create(
                    user_id=self.user.id,
                    defaults={'location': cleaned_location_data}
                )
                
                # 3. Create the new trail record (raw location + snapped cleaned_location)
                DriverTrail.objects.create(
                    user_id=self.user.id,
                    location=location_data,
                    cleaned_location=cleaned_location_data
                )

                # 4. Fetch history and build continuous street-snapped route path
                from django.utils import timezone
                from datetime import timedelta
                
                time_threshold = timezone.now() - timedelta(hours=12)
                historical_trails = DriverTrail.objects.filter(
                    user_id=self.user.id,
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
                    from routing.services.osrm_client import get_road_route
                    return get_road_route(unique_coords)
                else:
                    return unique_coords

        except Exception as e:
            print(f"[DB Sync Error] {str(e)}")
            traceback.print_exc()
            return []

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
                    
                    # Fetch their trail
                    trails = DriverTrail.objects.filter(
                        user=driver,
                        timestamp__gte=time_threshold
                    ).order_by('timestamp')
                    
                    trail_points = []
                    for t in trails:
                        point_loc = t.cleaned_location or t.location
                        if hasattr(point_loc, 'x'):
                            trail_points.append([point_loc.x, point_loc.y])
                        elif isinstance(point_loc, dict):
                            trail_points.append([point_loc.get('lng'), point_loc.get('lat')])
                    
                    # Filter out consecutive duplicates to optimize OSRM payload
                    unique_coords = []
                    for coord in trail_points:
                        if not unique_coords or unique_coords[-1] != coord:
                            unique_coords.append(coord)
                            
                    # Route along streets to avoid straight-line jumps cutting through blocks
                    if len(unique_coords) >= 2:
                        from routing.services.osrm_client import get_road_route
                        trail_points = get_road_route(unique_coords)
                    else:
                        trail_points = unique_coords
                    
                    # Snapped lat/lng of current position
                    current_lat = loc.location.y if hasattr(loc.location, 'y') else loc.location.get('lat')
                    current_lng = loc.location.x if hasattr(loc.location, 'x') else loc.location.get('lng')
                    
                    drivers_state.append({
                        "driver_id": str(driver.id),
                        "driver_name": driver.get_full_name() or driver.username,
                        "lat": current_lat,
                        "lng": current_lng,
                        "trail": trail_points
                    })
                return drivers_state
        except Exception as e:
            print(f"[Initial State Error] {str(e)}")
            traceback.print_exc()
            return []
