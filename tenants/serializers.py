from rest_framework import serializers
from .models import City, Zone, HolidayCalendar


class CitySerializer(serializers.ModelSerializer):
    class Meta:
        model = City
        fields = ['id', 'schema_name', 'name', 'state', 'code', 'is_active', 'timezone', 'created_at']
        read_only_fields = ['id', 'created_at']


class ZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Zone
        fields = ['id', 'name', 'boundary', 'description', 'is_active']


class HolidayCalendarSerializer(serializers.ModelSerializer):
    class Meta:
        model = HolidayCalendar
        fields = ['id', 'name', 'date', 'is_recurring', 'description']
