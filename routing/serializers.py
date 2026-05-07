from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer
from .models import Route, Driver, TrackingEvent, DailyReconciliation


class DriverSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = Driver
        fields = ['id', 'user', 'full_name', 'vehicle_plate', 'vehicle_type',
                  'max_capacity_kg', 'is_available']

    def get_full_name(self, obj):
        try:
            return obj.user.get_full_name() if obj.user else "Unknown User"
        except Exception:
            return "User Profile Error"


class TrackingEventSerializer(serializers.ModelSerializer):
    collection_method_display = serializers.CharField(source='get_collection_method_display', read_only=True)

    class Meta:
        model = TrackingEvent
        fields = [
            'id', 'route', 'order', 'status', 'location', 'notes', 'timestamp',
            'photo_proof', 'collection_amount', 'collection_method', 
            'collection_method_display', 'customer_signature'
        ]
        read_only_fields = ['id', 'timestamp']


class RouteSerializer(serializers.ModelSerializer):
    driver_name = serializers.CharField(source='driver.user.get_full_name', read_only=True)
    order_ids = serializers.PrimaryKeyRelatedField(
        source='orders', many=True, read_only=True
    )

    class Meta:
        model = Route
        fields = [
            'id', 'driver', 'driver_name', 'order_ids', 'status',
            'geometry', 'waypoints', 'estimated_duration_minutes',
            'estimated_distance_km', 'optimization_error',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'status', 'geometry', 'waypoints',
            'estimated_duration_minutes', 'estimated_distance_km',
            'optimization_error', 'created_at', 'updated_at',
        ]


class RouteGeoSerializer(GeoFeatureModelSerializer):
    class Meta:
        model = Route
        geo_field = 'geometry'
        fields = ['id', 'driver', 'status', 'estimated_duration_minutes', 'waypoints']


class DailyReconciliationSerializer(serializers.ModelSerializer):
    driver_name = serializers.CharField(source='driver.user.get_full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    reconciled_by_name = serializers.CharField(source='reconciled_by.get_full_name', read_only=True)

    class Meta:
        model = DailyReconciliation
        fields = [
            'id', 'driver', 'driver_name', 'route', 'date',
            'total_cash_collected', 'total_upi_collected', 'total_wallet_deducted',
            'expected_total', 'actual_total', 'discrepancy', 'status', 
            'status_display', 'reconciled_by', 'reconciled_by_name', 'notes', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class ReconcileActionSerializer(serializers.Serializer):
    actual_total = serializers.DecimalField(max_digits=12, decimal_places=2)
    notes = serializers.CharField(required=False, allow_blank=True)
