from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer
from .models import Route, Driver, TrackingEvent, DailyReconciliation, Zone


class ZoneSerializer(serializers.ModelSerializer):
    driver_name = serializers.CharField(source='assigned_driver.get_full_name', read_only=True)
    
    # Use GeometryField to correctly parse the GeoJSON from Postman
    from rest_framework_gis.fields import GeometryField
    boundary = GeometryField(required=False, allow_null=True)

    class Meta:
        model = Zone
        fields = ['id', 'name', 'description', 'boundary', 'assigned_driver', 'driver_name', 'is_active']
        read_only_fields = ['id', 'driver_name']

    def validate(self, data):
        from django.db import connection
        from rest_framework import serializers
        
        boundary = data.get('boundary')
        city = connection.tenant
        
        # Geofencing Validation
        if boundary and city and hasattr(city, 'boundary') and city.boundary:
            if not city.boundary.contains(boundary):
                raise serializers.ValidationError({
                    "boundary": f"This zone boundary is outside the permitted city limits for {city.name}."
                })
                
        return data

    def create(self, validated_data):
        # Extra safety: ensure 'city' doesn't cause a TypeError
        validated_data.pop('city', None)
        return super().create(validated_data)


class DriverSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    current_route = serializers.SerializerMethodField()

    class Meta:
        model = Driver
        fields = ['id', 'user', 'full_name', 'vehicle_plate', 'vehicle_type',
                  'max_capacity_kg', 'is_available', 'on_trip', 'zone', 'current_route']

    def get_full_name(self, obj):
        try:
            return obj.user.get_full_name() if obj.user else "Unknown User"
        except Exception:
            return "User Profile Error"

    def get_current_route(self, obj):
        # Look for the most recent route that isn't completed or failed
        route = obj.routes.filter(status__in=['pending', 'in_progress']).first()
        return route.id if route else None

    def create(self, validated_data):
        from django.db import connection
        from hr.models import Employee, Department
        from django.utils import timezone
        
        zone = validated_data.get('zone')
        driver = super().create(validated_data)
        
        # 1. Sync the tenant_schema back to the User model
        user = driver.user
        if user:
            user.tenant_schema = connection.schema_name
            user.save()
            
        # 2. Automatically create an Employee record in the HR module
        logistics_dept, _ = Department.objects.get_or_create(
            name="Logistics",
            defaults={"description": "Fleet and delivery management."}
        )
        
        # Generate a unique Employee ID for the driver
        import random
        emp_id = f"DRV-{timezone.now().year}-{random.randint(1000, 9999)}"
        
        Employee.objects.get_or_create(
            user=user,
            defaults={
                "department": logistics_dept,
                "job_title": "Delivery Driver",
                "employee_id": emp_id,
                "date_joined": timezone.now().date(),
                "is_active": True
            }
        )
            
        # 3. If a zone was provided, set this driver as the primary driver for that zone
        if zone:
            zone.assigned_driver = user
            zone.save()
            
        return driver


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
