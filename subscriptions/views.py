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
            if not sub_id:
                continue
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
        subscription.pause_updated_by = request.user
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
        subscription.pause_updated_by = request.user
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

    # ──────────────────────────────────────────────────────────────
    # MONTHLY DELIVERY CALENDAR ENDPOINTS
    # ──────────────────────────────────────────────────────────────

    @action(detail=True, methods=['get'], url_path='monthly-summary')
    def monthly_summary(self, request, pk=None):
        """
        Returns a day-by-day delivery calendar for ONE specific subscription.

        Query params:
            year  (int)  – defaults to current year
            month (int)  – defaults to current month (1–12)

        Day statuses (for frontend calendar colour-coding):
            not_active  – day is outside subscription start/end date
            vacation    – day falls within a paused/vacation range
            skipped     – customer requested a skip for this specific date
            off_day     – subscription frequency doesn't include this day
            delivered   – order exists and is marked as delivered  ✅
            undelivered – order was cancelled OR past date with no order ❌
            pending     – order exists but still in progress (confirmed/dispatched)
            scheduled   – delivery expected on a future date (no order yet)

        Accessible by: Admin and the owning Customer.
        """
        import datetime
        import calendar
        from orders.models import Order, OrderStatus

        subscription = self.get_object()

        # --- Parse & validate year/month ---
        today = datetime.date.today()
        try:
            year = int(request.query_params.get('year', today.year))
            month = int(request.query_params.get('month', today.month))
            if not (1 <= month <= 12):
                raise ValueError
        except (ValueError, TypeError):
            return Response(
                {'detail': 'Invalid year or month. Use ?year=YYYY&month=M'},
                status=status.HTTP_400_BAD_REQUEST
            )

        month_start = datetime.date(year, month, 1)
        month_end = datetime.date(year, month, calendar.monthrange(year, month)[1])

        # --- Pre-fetch: orders for this subscription in the month ---
        orders_qs = Order.objects.filter(
            subscription=subscription,
            scheduled_delivery_date__range=(month_start, month_end)
        ).values('scheduled_delivery_date', 'id', 'status')

        order_map = {
            o['scheduled_delivery_date']: {
                'order_id': str(o['id']),
                'order_status': o['status'],
            }
            for o in orders_qs
        }

        # --- Pre-fetch: customer skip dates for this subscription in the month ---
        skip_dates = set(
            SubscriptionSkipDate.objects
            .filter(subscription=subscription, skip_date__range=(month_start, month_end))
            .values_list('skip_date', flat=True)
        )

        # --- Build daily calendar ---
        daily = []
        counts = {
            'total_scheduled':   0,  # days delivery was expected
            'total_delivered':   0,
            'total_undelivered': 0,
            'total_in_transit':  0,  # driver started trip, delivery en-route
            'total_pending':     0,  # order created, not yet dispatched
            'total_skipped':     0,
            'total_vacation':    0,
            'total_off_days':    0,
            'total_not_active':  0,
        }

        total_days = calendar.monthrange(year, month)[1]

        for day_num in range(1, total_days + 1):
            day = datetime.date(year, month, day_num)
            entry = {'date': day.isoformat()}

            # 1. Outside subscription active period?
            if day < subscription.start_date:
                entry['status'] = 'not_active'
                counts['total_not_active'] += 1
                daily.append(entry)
                continue

            if subscription.end_date and day > subscription.end_date:
                entry['status'] = 'not_active'
                counts['total_not_active'] += 1
                daily.append(entry)
                continue

            # 2. Vacation / pause range?
            if subscription.pause_start and subscription.pause_end:
                if subscription.pause_start <= day <= subscription.pause_end:
                    entry['status'] = 'vacation'
                    counts['total_vacation'] += 1
                    daily.append(entry)
                    continue

            # 3. Customer-requested skip date?
            if day in skip_dates:
                entry['status'] = 'skipped'
                counts['total_skipped'] += 1
                daily.append(entry)
                continue

            # 4. Does the frequency include this day?
            if not subscription.should_deliver_on(day):
                entry['status'] = 'off_day'
                counts['total_off_days'] += 1
                daily.append(entry)
                continue

            # 5. Delivery was expected — check actual order record
            counts['total_scheduled'] += 1

            if day in order_map:
                order_info = order_map[day]
                entry['order_id'] = order_info['order_id']
                entry['order_status'] = order_info['order_status']

                if order_info['order_status'] == OrderStatus.DELIVERED:
                    entry['status'] = 'delivered'
                    counts['total_delivered'] += 1
                elif order_info['order_status'] in [OrderStatus.CANCELLED, OrderStatus.UNDELIVERED]:
                    entry['status'] = 'undelivered'
                    counts['total_undelivered'] += 1
                elif order_info['order_status'] == OrderStatus.IN_TRANSIT:
                    # Driver started the trip — delivery is en-route
                    entry['status'] = 'in_transit'
                    counts['total_in_transit'] += 1
                else:
                    # confirmed / dispatched — not yet on the road
                    entry['status'] = 'pending'
                    counts['total_pending'] += 1
            else:
                # No order record at all
                if day <= today:
                    # Past date with no order = missed/undelivered
                    entry['status'] = 'undelivered'
                    counts['total_undelivered'] += 1
                else:
                    # Future date — order not yet generated
                    entry['status'] = 'scheduled'

            daily.append(entry)

        # --- Items being delivered under this subscription ---
        items = [
            {
                'product_id': str(i.product_id),
                'product_name': i.product.name,
                'quantity': i.quantity,
            }
            for i in subscription.items.select_related('product').all()
        ]

        return Response({
            'subscription_id': str(subscription.id),
            'customer_id': str(subscription.customer_id),
            'customer_name': subscription.customer.name,
            'year': year,
            'month': month,
            'frequency': subscription.frequency,
            'frequency_display': subscription.get_frequency_display(),
            'is_paused': subscription.is_paused,
            'pause_start': subscription.pause_start,
            'pause_end': subscription.pause_end,
            'subscription_start': subscription.start_date.isoformat(),
            'subscription_end': subscription.end_date.isoformat() if subscription.end_date else None,
            'items': items,
            'summary': counts,
            'daily': daily,
        })

    @action(detail=False, methods=['get'], url_path='customer-monthly-summary')
    def customer_monthly_summary(self, request):
        """
        Returns monthly delivery calendar across ALL subscriptions of a customer.
        Admin uses this to view any customer; customers use it for their own account.

        Query params:
            customer_id (uuid)  – required
            year        (int)   – defaults to current year
            month       (int)   – defaults to current month

        Response merges daily status across all subscriptions of the customer.
        If a customer has multiple subscriptions (e.g. milk + curd), each is
        returned separately under 'subscriptions[]', plus an overall_summary.
        """
        import datetime
        import calendar
        from orders.models import Order, OrderStatus

        customer_id = request.query_params.get('customer_id')
        if not customer_id:
            return Response(
                {'detail': 'customer_id query parameter is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        today = datetime.date.today()
        try:
            year = int(request.query_params.get('year', today.year))
            month = int(request.query_params.get('month', today.month))
            if not (1 <= month <= 12):
                raise ValueError
        except (ValueError, TypeError):
            return Response(
                {'detail': 'Invalid year or month. Use ?year=YYYY&month=M'},
                status=status.HTTP_400_BAD_REQUEST
            )

        subscriptions = Subscription.objects.filter(
            customer_id=customer_id
        ).prefetch_related('items__product', 'skip_dates')

        if not subscriptions.exists():
            return Response(
                {'detail': 'No subscriptions found for this customer.'},
                status=status.HTTP_404_NOT_FOUND
            )

        month_start = datetime.date(year, month, 1)
        month_end = datetime.date(year, month, calendar.monthrange(year, month)[1])
        total_days = calendar.monthrange(year, month)[1]

        # Aggregate counts across ALL subscriptions
        overall_counts = {
            'total_scheduled':   0,
            'total_delivered':   0,
            'total_undelivered': 0,
            'total_in_transit':  0,
            'total_pending':     0,
            'total_skipped':     0,
            'total_vacation':    0,
        }

        subscriptions_data = []

        for sub in subscriptions:
            orders_qs = Order.objects.filter(
                subscription=sub,
                scheduled_delivery_date__range=(month_start, month_end)
            ).values('scheduled_delivery_date', 'id', 'status')

            order_map = {
                o['scheduled_delivery_date']: {
                    'order_id': str(o['id']),
                    'order_status': o['status'],
                }
                for o in orders_qs
            }

            skip_dates = set(
                sub.skip_dates
                .filter(skip_date__range=(month_start, month_end))
                .values_list('skip_date', flat=True)
            )

            sub_counts = {
                'total_scheduled':   0,
                'total_delivered':   0,
                'total_undelivered': 0,
                'total_in_transit':  0,
                'total_pending':     0,
                'total_skipped':     0,
                'total_vacation':    0,
                'total_off_days':    0,
                'total_not_active':  0,
            }
            daily = []

            for day_num in range(1, total_days + 1):
                day = datetime.date(year, month, day_num)
                entry = {'date': day.isoformat()}

                if day < sub.start_date or (sub.end_date and day > sub.end_date):
                    entry['status'] = 'not_active'
                    sub_counts['total_not_active'] += 1
                    daily.append(entry)
                    continue

                if sub.pause_start and sub.pause_end:
                    if sub.pause_start <= day <= sub.pause_end:
                        entry['status'] = 'vacation'
                        sub_counts['total_vacation'] += 1
                        overall_counts['total_vacation'] += 1
                        daily.append(entry)
                        continue

                if day in skip_dates:
                    entry['status'] = 'skipped'
                    sub_counts['total_skipped'] += 1
                    overall_counts['total_skipped'] += 1
                    daily.append(entry)
                    continue

                if not sub.should_deliver_on(day):
                    entry['status'] = 'off_day'
                    sub_counts['total_off_days'] += 1
                    daily.append(entry)
                    continue

                sub_counts['total_scheduled'] += 1
                overall_counts['total_scheduled'] += 1

                if day in order_map:
                    order_info = order_map[day]
                    entry['order_id'] = order_info['order_id']
                    entry['order_status'] = order_info['order_status']

                    if order_info['order_status'] == OrderStatus.DELIVERED:
                        entry['status'] = 'delivered'
                        sub_counts['total_delivered'] += 1
                        overall_counts['total_delivered'] += 1
                    elif order_info['order_status'] in [OrderStatus.CANCELLED, OrderStatus.UNDELIVERED]:
                        entry['status'] = 'undelivered'
                        sub_counts['total_undelivered'] += 1
                        overall_counts['total_undelivered'] += 1
                    elif order_info['order_status'] == OrderStatus.IN_TRANSIT:
                        # Driver started trip — delivery is en-route
                        entry['status'] = 'in_transit'
                        sub_counts['total_in_transit'] += 1
                        overall_counts['total_in_transit'] += 1
                    else:
                        entry['status'] = 'pending'
                        sub_counts['total_pending'] += 1
                        overall_counts['total_pending'] += 1
                else:
                    if day <= today:
                        entry['status'] = 'undelivered'
                        sub_counts['total_undelivered'] += 1
                        overall_counts['total_undelivered'] += 1
                    else:
                        entry['status'] = 'scheduled'

                daily.append(entry)

            items = [
                {
                    'product_id': str(i.product_id),
                    'product_name': i.product.name,
                    'quantity': i.quantity,
                }
                for i in sub.items.all()
            ]

            subscriptions_data.append({
                'subscription_id': str(sub.id),
                'frequency': sub.frequency,
                'frequency_display': sub.get_frequency_display(),
                'status': sub.status,
                'is_paused': sub.is_paused,
                'pause_start': sub.pause_start,
                'pause_end': sub.pause_end,
                'subscription_start': sub.start_date.isoformat(),
                'subscription_end': sub.end_date.isoformat() if sub.end_date else None,
                'items': items,
                'summary': sub_counts,
                'daily': daily,
            })

        customer = subscriptions.first().customer
        return Response({
            'customer_id': str(customer.id),
            'customer_name': customer.name,
            'customer_email': customer.email,
            'year': year,
            'month': month,
            'overall_summary': overall_counts,
            'subscriptions': subscriptions_data,
        })
