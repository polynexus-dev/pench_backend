from rest_framework import serializers
from django.contrib.gis.geos import Point
from .models import Customer, Lead


class CustomerSerializer(serializers.ModelSerializer):
    latitude = serializers.FloatField(required=False)
    longitude = serializers.FloatField(required=False)

    class Meta:
        model = Customer
        fields = [
            'id', 'name', 'company', 'email', 'phone', 'address',
            'latitude', 'longitude', 'notes', 'is_active', 
            'qr_code_id', 'created_at'
        ]
        read_only_fields = ['id', 'qr_code_id', 'created_at']

    def to_representation(self, instance):
        """
        Convert the GIS location back to lat/lng for output.
        """
        ret = super().to_representation(instance)
        if instance.location:
            ret['latitude'] = instance.location.y
            ret['longitude'] = instance.location.x
        return ret

    def create(self, validated_data):
        lat = validated_data.pop('latitude', None)
        lng = validated_data.pop('longitude', None)
        
        if lat is not None and lng is not None:
            validated_data['location'] = Point(lng, lat)
            
        return super().create(validated_data)

    def update(self, instance, validated_data):
        lat = validated_data.pop('latitude', None)
        lng = validated_data.pop('longitude', None)
        
        if lat is not None and lng is not None:
            instance.location = Point(lng, lat)
            
        return super().update(instance, validated_data)


class LeadSerializer(serializers.ModelSerializer):
    referred_by_name = serializers.CharField(source='referred_by.name', read_only=True)

    class Meta:
        model = Lead
        fields = ['id', 'name', 'phone', 'email', 'referred_by', 'referred_by_name', 'notes', 'status', 'created_at']
        read_only_fields = ['id', 'created_at']
