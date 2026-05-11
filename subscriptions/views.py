from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Subscription, SubscriptionSkipDate
from .serializers import SubscriptionSerializer, SubscriptionSkipDateSerializer


class SubscriptionViewSet(viewsets.ModelViewSet):
    queryset = Subscription.objects.all().prefetch_related('items__product')
    serializer_class = SubscriptionSerializer
    filterset_fields = ['status', 'frequency', 'is_paused', 'customer']

    def create(self, request, *args, **kwargs):
        """
        Supports creating multiple subscriptions in one request.
        """
        from django.db import connection
        print(f"[DEBUG] Create Subscriptions hit. Schema: {connection.schema_name}")
        print(f"[DEBUG] Payload Type: {type(request.data)}")
        print(f"[DEBUG] Payload Data: {request.data}")

        is_many = isinstance(request.data, list)
        if not is_many:
            return super().create(request, *args, **kwargs)
        
        serializer = self.get_serializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        
        print(f"[DEBUG] Created {len(serializer.data)} subscriptions.")
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['patch', 'put'])
    def bulk_update(self, request):
        """
        Updates multiple subscriptions at once. Each must have an 'id'.
        """
        data = request.data
        if not isinstance(data, list):
            return Response({"detail": "Expected a list."}, status=status.HTTP_400_BAD_REQUEST)

        updated = []
        for item in data:
            sub_id = item.get('id')
            if not sub_id: continue
            try:
                instance = Subscription.objects.get(id=sub_id)
                serializer = self.get_serializer(instance, data=item, partial=True)
                serializer.is_valid(raise_exception=True)
                serializer.save()
                updated.append(serializer.data)
            except Subscription.DoesNotExist:
                continue
        return Response(updated, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='pause')
    def pause(self, request, pk=None):
        subscription = self.get_object()
        pause_start = request.data.get('pause_start')
        pause_end = request.data.get('pause_end')
        
        if not pause_start or not pause_end:
            return Response({'detail': 'pause_start and pause_end are required.'}, status=400)
            
        subscription.is_paused = True
        subscription.pause_start = pause_start
        subscription.pause_end = pause_end
        subscription.save()
        
        return Response(SubscriptionSerializer(subscription).data)

    @action(detail=True, methods=['post'], url_path='vacation')
    def vacation(self, request, pk=None):
        """ Alias for pause with a more user-friendly name. """
        return self.pause(request, pk)

    @action(detail=True, methods=['post'], url_path='resume')
    def resume(self, request, pk=None):
        subscription = self.get_object()
        subscription.is_paused = False
        subscription.pause_start = None
        subscription.pause_end = None
        subscription.save()
        return Response(SubscriptionSerializer(subscription).data)

    @action(detail=True, methods=['post'], url_path='update-quantity')
    def update_quantity(self, request, pk=None):
        """ Update the quantity for a specific product in the subscription. """
        subscription = self.get_object()
        product_id = request.data.get('product_id')
        new_quantity = request.data.get('quantity')

        if product_id is None or new_quantity is None:
            return Response({'detail': 'product_id and quantity are required.'}, status=400)

        from .models import SubscriptionItem
        item = SubscriptionItem.objects.filter(subscription=subscription, product_id=product_id).first()
        if not item:
            return Response({'detail': 'Product not found in this subscription.'}, status=404)

        item.quantity = int(new_quantity)
        item.save()
        
        return Response(SubscriptionSerializer(subscription).data)

    @action(detail=True, methods=['post'], url_path='add-skip-date')
    def add_skip_date(self, request, pk=None):
        subscription = self.get_object()
        skip_date = request.data.get('skip_date')
        reason = request.data.get('reason', '')
        
        if not skip_date:
            return Response({'detail': 'skip_date is required.'}, status=400)
            
        skip_obj, created = SubscriptionSkipDate.objects.get_or_create(
            subscription=subscription,
            skip_date=skip_date,
            defaults={'reason': reason}
        )
        
        return Response(SubscriptionSkipDateSerializer(skip_obj).data)
        
    @action(detail=False, methods=['post'], url_path='trigger-generation')
    def trigger_generation(self, request):
        """
        Manually trigger order generation for testing.
        """
        from .tasks import generate_city_orders
        target_date = request.data.get('target_date')
        
        import datetime
        if target_date:
            target_date = datetime.date.fromisoformat(target_date)
        else:
            target_date = datetime.date.today() + datetime.timedelta(days=1)
            
        stats = generate_city_orders(target_date)
        return Response(stats)
