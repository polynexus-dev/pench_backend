from rest_framework import viewsets, serializers
from rest_framework.permissions import IsAuthenticated
from core.permissions import IsERPUser
from .models import DriverLocation


class DriverLocationSerializer(serializers.ModelSerializer):
    driver_name = serializers.CharField(source='user.get_full_name', read_only=True)
    lat = serializers.FloatField(source='location.y', read_only=True)
    lng = serializers.FloatField(source='location.x', read_only=True)

    class Meta:
        model = DriverLocation
        fields = ['id', 'user', 'driver_name', 'lat', 'lng', 'updated_at']


class DriverLocationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API for Admins to see the live location of all drivers.
    """
    queryset = DriverLocation.objects.all().select_related('user')
    serializer_class = DriverLocationSerializer
    permission_classes = [IsERPUser]
