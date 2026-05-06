from django.contrib.gis import admin
from .models import Route, Driver, TrackingEvent, DailyReconciliation

@admin.register(Route)
class RouteAdmin(admin.GISModelAdmin):
    list_display = ['id', 'driver', 'status', 'estimated_duration_minutes', 'created_at']
    list_filter = ['status']

@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = ['user', 'vehicle_plate', 'vehicle_type', 'is_available']
    list_filter = ['is_available']

@admin.register(TrackingEvent)
class TrackingEventAdmin(admin.GISModelAdmin):
    list_display = ['route', 'order', 'status', 'collection_method', 'collection_amount', 'timestamp']
    list_filter = ['status', 'collection_method']

@admin.register(DailyReconciliation)
class DailyReconciliationAdmin(admin.ModelAdmin):
    list_display = ['driver', 'date', 'expected_total', 'actual_total', 'discrepancy', 'status']
    list_filter = ['status', 'date']
    search_fields = ['driver__user__first_name', 'notes']
