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
        return [[t.location.x, t.location.y] for t in trails]


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

        # Build LineString coordinates and collect timestamps
        coords = []
        timestamps = []
        for t in trails:
            coords.append([t.location.x, t.location.y])
            timestamps.append(t.timestamp.strftime('%H:%M:%S'))
        
        # If only one point, we can't make a LineString, return a Point
        if len(coords) < 2:
            geometry = {
                "type": "Point",
                "coordinates": coords[0]
            }
        else:
            geometry = {
                "type": "LineString",
                "coordinates": coords
            }

        return Response({
            "type": "Feature",
            "geometry": geometry,
            "properties": {
                "driver_id": driver.id,
                "driver_name": driver.get_full_name(),
                "date": str(date),
                "point_count": len(coords),
                "timestamps": timestamps # Array of times matching the coordinates
            }
        })
