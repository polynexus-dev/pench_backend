from rest_framework import serializers
from django.contrib.gis.geos import Point
from .models import Customer, Lead


class CustomerSerializer(serializers.ModelSerializer):
    latitude = serializers.FloatField(required=False, allow_null=True)
    longitude = serializers.FloatField(required=False, allow_null=True)

    class Meta:
        model = Customer
        fields = [
            'id', 'name', 'company', 'email', 'phone', 'address',
            'latitude', 'longitude', 'notes', 'is_active', 
            'qr_code_id', 'created_at'
        ]
        read_only_fields = ['id', 'qr_code_id', 'created_at']

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        # Ensure they always exist in the output
        ret['latitude'] = instance.location.y if instance.location else None
        ret['longitude'] = instance.location.x if instance.location else None
        return ret

    def create(self, validated_data):
        # Support multiple field name variations for input
        lat = validated_data.pop('latitude', None)
        lng = validated_data.pop('longitude', None)
        
        # Check request for 'lat'/'lng' aliases if not in validated_data
        if lat is None:
            lat = self.context['request'].data.get('lat')
        if lng is None:
            lng = self.context['request'].data.get('lng')

        if lat is not None and lng is not None:
            try:
                validated_data['location'] = Point(float(lng), float(lat))
            except (ValueError, TypeError):
                pass
            
        return super().create(validated_data)

    def update(self, instance, validated_data):
        lat = validated_data.pop('latitude', None)
        lng = validated_data.pop('longitude', None)
        
        if lat is None:
            lat = self.context['request'].data.get('lat')
        if lng is None:
            lng = self.context['request'].data.get('lng')

        if lat is not None and lng is not None:
            try:
                instance.location = Point(float(lng), float(lat))
            except (ValueError, TypeError):
                pass
            
        return super().update(instance, validated_data)


class LeadSerializer(serializers.ModelSerializer):
    referred_by_name = serializers.CharField(source='referred_by.name', read_only=True)

    class Meta:
        model = Lead
        fields = ['id', 'name', 'phone', 'email', 'referred_by', 'referred_by_name', 'notes', 'status', 'created_at']
        read_only_fields = ['id', 'created_at']
