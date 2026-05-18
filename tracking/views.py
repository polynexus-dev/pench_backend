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

    class Meta:
        model = DriverLocation
        fields = ['id', 'user', 'driver_name', 'lat', 'lng', 'trail', 'updated_at']

    def get_trail(self, obj):
        import datetime
        today = datetime.date.today()
        trails = DriverTrail.objects.filter(
            user=obj.user,
            timestamp__date=today
        ).order_by('timestamp')
        
        # Use pre-cleaned location if available, otherwise raw
        return [
            [t.cleaned_location.x, t.cleaned_location.y] if t.cleaned_location else [t.location.x, t.location.y]
            for t in trails
        ]


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
        """
        location_obj = self.get_object()
        driver = location_obj.user
        
        date_str = request.query_params.get('date')
        if date_str:
            date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
        else:
            date = datetime.date.today()

        # Fetch all points for this driver on this day
        trails = DriverTrail.objects.filter(
            user=driver,
            timestamp__date=date
        ).order_by('timestamp')

        if not trails.exists():
            return Response({
                "type": "Feature",
                "geometry": None,
                "properties": {"message": "No trail found for this date."}
            })

        # Build coordinates using the pre-cleaned data from DB
        coords = []
        for t in trails:
            loc = t.cleaned_location or t.location
            coords.append([loc.x, loc.y])
        
        # Generate continuous curved road geometry using OSRM Route
        from routing.services.osrm_client import get_road_route
        
        # OSRM has a limit on waypoints in the URL (usually 100)
        # Downsample coordinates if there are too many, OSRM will route between them anyway
        if len(coords) > 90:
            step = len(coords) // 90 + 1
            sampled_coords = coords[::step]
            if sampled_coords[-1] != coords[-1]:
                sampled_coords.append(coords[-1])
        else:
            sampled_coords = coords
            
        route_coords = get_road_route(sampled_coords) if len(sampled_coords) > 1 else coords
        
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
                "date": str(date),
                "point_count": len(coords),
            }
        })
