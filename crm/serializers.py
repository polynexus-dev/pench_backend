from rest_framework import serializers
from .models import Customer, Lead, HAS_GIS


try:
    from django.contrib.gis.geos import Point
except ImportError:
    Point = None


class CustomerSerializer(serializers.ModelSerializer):
    latitude = serializers.FloatField(required=False, allow_null=True)
    longitude = serializers.FloatField(required=False, allow_null=True)
    dashboard = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = [
            'id', 'name', 'company', 'email', 'phone', 'address',
            'latitude', 'longitude', 'notes', 'is_active', 
            'qr_code_id', 'created_at', 'dashboard'
        ]
        read_only_fields = ['id', 'qr_code_id', 'created_at']

    def get_dashboard(self, obj):
        """Aggregates metrics for the customer within the current schema."""
        from subscriptions.models import Subscription, SubscriptionStatus
        from finance.models import MonthlyBill, BillStatus
        from orders.models import Order
        
        # 1. Active Subscriptions
        active_subs = Subscription.objects.filter(
            customer=obj, 
            status=SubscriptionStatus.ACTIVE
        ).count()
        
        # 2. Pending Balance
        bills = MonthlyBill.objects.filter(
            customer=obj
        ).exclude(status=BillStatus.CANCELLED)
        
        total_pending = sum((bill.total_amount - bill.amount_paid) for bill in bills)
        
        # 3. Total Orders
        total_orders = Order.objects.filter(customer=obj).count()
        
        return {
            "active_subscriptions": active_subs,
            "pending_balance": float(total_pending),
            "total_orders": total_orders
        }

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        loc = instance.location
        
        # Default to None
        ret['latitude'] = None
        ret['longitude'] = None
        
        if loc:
            # Case 1: GEOS Point object
            if hasattr(loc, 'x') and hasattr(loc, 'y'):
                ret['latitude'] = loc.y
                ret['longitude'] = loc.x
            # Case 2: Dictionary (JSONField fallback)
            elif isinstance(loc, dict):
                ret['latitude'] = loc.get('latitude') or loc.get('lat')
                ret['longitude'] = loc.get('longitude') or loc.get('lng')
            # Case 3: String (likely WKT or EWKB hex)
            elif isinstance(loc, str) and Point:
                try:
                    # Try to parse WKT string if possible
                    p = Point.from_ewkt(loc) if 'SRID' in loc else Point(loc)
                    ret['latitude'] = p.y
                    ret['longitude'] = p.x
                except Exception:
                    pass
                    
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
            if HAS_GIS and Point:
                try:
                    validated_data['location'] = Point(float(lng), float(lat))
                except (ValueError, TypeError):
                    pass
            else:
                validated_data['location'] = {'lat': float(lat), 'lng': float(lng)}
            
        return super().create(validated_data)

    def update(self, instance, validated_data):
        lat = validated_data.pop('latitude', None)
        lng = validated_data.pop('longitude', None)
        
        if lat is None:
            lat = self.context['request'].data.get('lat')
        if lng is None:
            lng = self.context['request'].data.get('lng')

        if lat is not None and lng is not None:
            if HAS_GIS and Point:
                try:
                    instance.location = Point(float(lng), float(lat))
                except (ValueError, TypeError):
                    pass
            else:
                instance.location = {'lat': float(lat), 'lng': float(lng)}
            
        return super().update(instance, validated_data)


class LeadSerializer(serializers.ModelSerializer):
    referred_by_name = serializers.CharField(source='referred_by.name', read_only=True)

    class Meta:
        model = Lead
        fields = ['id', 'name', 'phone', 'email', 'referred_by', 'referred_by_name', 'notes', 'status', 'created_at']
        read_only_fields = ['id', 'created_at']
