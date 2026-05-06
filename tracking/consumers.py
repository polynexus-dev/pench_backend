import json
import traceback
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.gis.geos import Point
from django_tenants.utils import schema_context
from .models import DriverLocation, DriverTrail


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
        except Exception as e:
            print(f"[WS Receive Error] CRASH: {str(e)}")
            traceback.print_exc()

    async def broadcast_location(self, event):
        await self.send(text_data=json.dumps(event))

    @database_sync_to_async
    def update_driver_location(self, lat, lng):
        try:
            with schema_context(self.tenant.schema_name):
                # Ensure float conversion and correct order (lng, lat)
                p_lng = float(lng)
                p_lat = float(lat)
                point = Point(p_lng, p_lat, srid=4326)
                
                # Update current live position
                DriverLocation.objects.update_or_create(
                    user_id=self.user.id, # Use ID directly to avoid object issues
                    defaults={'location': point}
                )
                
                # Log trail breadcrumb
                DriverTrail.objects.create(
                    user_id=self.user.id,
                    location=point
                )

                # Fetch full trail for today to send to frontend
                import datetime
                today = datetime.date.today()
                trails = DriverTrail.objects.filter(
                    user_id=self.user.id,
                    timestamp__date=today
                ).order_by('timestamp')
                
                return [[t.location.x, t.location.y] for t in trails]
        except Exception as e:
            print(f"[DB Sync Error] {str(e)}")
            traceback.print_exc()
            return []
