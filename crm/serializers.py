from rest_framework import serializers
from django.contrib.gis.geos import Point
from .models import Customer, Lead


class CustomerSerializer(serializers.ModelSerializer):
    latitude = serializers.SerializerMethodField()
    longitude = serializers.SerializerMethodField()
    
    # Allow setting location via lat/lng fields
    lat = serializers.FloatField(write_only=True, required=False)
    lng = serializers.FloatField(write_only=True, required=False)

    class Meta:
        model = Customer
        fields = [
            'id', 'name', 'company', 'email', 'phone', 'address',
            'latitude', 'longitude', 'lat', 'lng', 'notes', 'is_active', 
            'qr_code_id', 'created_at'
        ]
        read_only_fields = ['id', 'qr_code_id', 'created_at']

    def get_latitude(self, obj):
        return obj.location.y if obj.location else None

    def get_longitude(self, obj):
        return obj.location.x if obj.location else None

    def create(self, validated_data):
        lat = validated_data.pop('lat', None)
        lng = validated_data.pop('lng', None)
        
        if lat is not None and lng is not None:
            validated_data['location'] = Point(lng, lat)
            
        return super().create(validated_data)

    def update(self, instance, validated_data):
        lat = validated_data.pop('lat', None)
        lng = validated_data.pop('lng', None)
        
        if lat is not None and lng is not None:
            instance.location = Point(lng, lat)
            
        return super().update(instance, validated_data)


class LeadSerializer(serializers.ModelSerializer):
    referred_by_name = serializers.CharField(source='referred_by.name', read_only=True)

    class Meta:
        model = Lead
        fields = ['id', 'name', 'phone', 'email', 'referred_by', 'referred_by_name', 'notes', 'status', 'created_at']
        read_only_fields = ['id', 'created_at']
