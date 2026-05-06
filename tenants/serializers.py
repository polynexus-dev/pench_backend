from rest_framework import serializers
from .models import City, Zone, HolidayCalendar


class CitySerializer(serializers.ModelSerializer):
    schema_name = serializers.CharField(required=False)

    class Meta:
        model = City
        fields = ['id', 'schema_name', 'name', 'state', 'code', 'is_active', 'timezone', 'created_at']
        read_only_fields = ['id', 'created_at']

    def create(self, validated_data):
        if not validated_data.get('schema_name'):
            name = validated_data.get('name', '').lower().replace(' ', '_')
            if name:
                validated_data['schema_name'] = name
            else:
                validated_data['schema_name'] = validated_data.get('code', '').lower()
        return super().create(validated_data)


class ZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Zone
        fields = ['id', 'name', 'boundary', 'description', 'is_active']


class HolidayCalendarSerializer(serializers.ModelSerializer):
    class Meta:
        model = HolidayCalendar
        fields = ['id', 'name', 'date', 'is_recurring', 'description']
