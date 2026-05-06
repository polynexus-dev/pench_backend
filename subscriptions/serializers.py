from rest_framework import serializers
from .models import Subscription, SubscriptionItem, SubscriptionSkipDate


class SubscriptionItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = SubscriptionItem
        fields = ['id', 'product', 'product_name', 'quantity']


class SubscriptionSkipDateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionSkipDate
        fields = ['id', 'skip_date', 'reason']


class SubscriptionSerializer(serializers.ModelSerializer):
    items = SubscriptionItemSerializer(many=True)
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    frequency_display = serializers.CharField(source='get_frequency_display', read_only=True)

    class Meta:
        model = Subscription
        fields = [
            'id', 'customer', 'customer_name', 'status', 'status_display',
            'frequency', 'frequency_display', 'custom_days', 
            'start_date', 'end_date', 'is_paused', 'pause_start', 'pause_end',
            'delivery_address', 'special_instructions', 'items'
        ]
        read_only_fields = ['id']

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        subscription = Subscription.objects.create(**validated_data)
        for item_data in items_data:
            SubscriptionItem.objects.create(subscription=subscription, **item_data)
        return subscription

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        instance = super().update(instance, validated_data)
        
        if items_data is not None:
            instance.items.all().delete()
            for item_data in items_data:
                SubscriptionItem.objects.create(subscription=instance, **item_data)
        
        return instance
