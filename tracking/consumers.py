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
                
                # 1. Update current live position
                DriverLocation.objects.update_or_create(
                    user_id=self.user.id,
                    defaults={'location': location_data}
                )
                
                # 2. Get the previous raw point for context (if any)
                prev_trail = DriverTrail.objects.filter(user_id=self.user.id).order_by('-timestamp').first()
                
                # 3. Create the new trail record (raw)
                new_trail = DriverTrail.objects.create(
                    user_id=self.user.id,
                    location=location_data
                )

                # 4. Snap to road using a SLIDING WINDOW of recent raw points for better context
                from routing.services.osrm_client import match_trail
                
                def get_coords(loc):
                    if hasattr(loc, 'x'): return [loc.x, loc.y]
                    if isinstance(loc, dict): return [loc.get('lng'), loc.get('lat')]
                    return [0, 0]

                # Get the last 4 raw points to provide context for the current one (Total 5 points)
                context_points = DriverTrail.objects.filter(
                    user_id=self.user.id
                ).order_by('-timestamp')[1:5] # Skip the one we just created
                
                # Convert to [lng, lat] and reverse to get chronological order
                coords_to_match = [get_coords(p.location) for p in reversed(context_points)]
                coords_to_match.append([p_lng, p_lat])
                
                if len(coords_to_match) >= 2:
                    # Provide a radius (e.g., 30 meters) to allow for GPS noise
                    radiuses = [30.0] * len(coords_to_match)
                    matched = match_trail(coords_to_match, radiuses=radiuses)
                    
                    # We take the LAST point of the matched sequence as the cleaned version of our CURRENT point
                    snapped_lng, snapped_lat = matched[-1]
                    
                    if HAS_GIS and Point:
                        new_trail.cleaned_location = Point(snapped_lng, snapped_lat, srid=4326)
                    else:
                        new_trail.cleaned_location = {'lat': snapped_lat, 'lng': snapped_lng}
                    new_trail.save(update_fields=['cleaned_location'])
                else:
                    # No context, just use the current one
                    new_trail.cleaned_location = location_data
                    new_trail.save(update_fields=['cleaned_location'])

                # 5. Fetch recent cleaned trails (last 12 hours) to send to frontend
                from django.utils import timezone
                from datetime import timedelta
                
                time_threshold = timezone.now() - timedelta(hours=12)
                trails = DriverTrail.objects.filter(
                    user_id=self.user.id,
                    timestamp__gte=time_threshold
                ).order_by('timestamp')
                
                def get_cleaned_coords(t):
                    loc = t.cleaned_location or t.location
                    if hasattr(loc, 'x'): return [loc.x, loc.y]
                    if isinstance(loc, dict): return [loc.get('lng'), loc.get('lat')]
                    return [0, 0]

                return [get_cleaned_coords(t) for t in trails]
        except Exception as e:
            print(f"[DB Sync Error] {str(e)}")
            traceback.print_exc()
            return []
