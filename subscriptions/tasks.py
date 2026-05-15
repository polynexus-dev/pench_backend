import logging
import datetime
from django.db import transaction, models
from django.utils import timezone
from celery import shared_task
from django_tenants.utils import schema_context
from .models import Subscription, SubscriptionStatus, SubscriptionSkipDate
from orders.models import Order, OrderItem, OrderStatus
from tenants.models import City, HolidayCalendar

logger = logging.getLogger(__name__)

@shared_task
def generate_all_tenant_orders(target_date_str=None):
    """
    Global task that iterates through all city tenants and generates orders.
    """
    if target_date_str:
        target_date = datetime.date.fromisoformat(target_date_str)
    else:
        target_date = datetime.date.today() + datetime.timedelta(days=1)
        
    cities = City.objects.exclude(schema_name='public')
    
    results = {}
    for city in cities:
        with schema_context(city.schema_name):
            try:
                stats = generate_city_orders(target_date)
                results[city.schema_name] = stats
            except Exception as e:
                logger.error(f"Error generating orders for {city.schema_name}: {str(e)}")
                results[city.schema_name] = {'error': str(e)}
                
    return results

def generate_city_orders(target_date):
    """
    Logic to generate orders for a specific city schema.
    """
    # 1. Check for city-wide holidays
    if HolidayCalendar.objects.filter(date=target_date).exists():
        logger.info(f"Skipping order generation for {target_date}: City holiday.")
        return {'status': 'skipped', 'reason': 'holiday'}

    # 2. Get active subscriptions
    active_subs = Subscription.objects.filter(
        status=SubscriptionStatus.ACTIVE,
        start_date__lte=target_date
    ).filter(
        models.Q(end_date__isnull=True) | models.Q(end_date__gte=target_date)
    ).prefetch_related('items__product', 'skip_dates')

    generated_count = 0
    skipped_count = 0
    
    for sub in active_subs:
        # Check frequency and pauses
        if not sub.should_deliver_on(target_date):
            skipped_count += 1
            continue
            
        # Check specific skip dates
        if sub.skip_dates.filter(skip_date=target_date).exists():
            skipped_count += 1
            continue
            
        # 3. Duplicate Prevention: Check if an order already exists for this sub and date
        if Order.objects.filter(subscription=sub, scheduled_delivery_date=target_date).exists():
            logger.info(f"Skipping: Order already exists for Sub {sub.id} on {target_date}")
            skipped_count += 1
            continue
            
        # 4. Create Order
        with transaction.atomic():
            order = Order.objects.create(
                customer=sub.customer,
                subscription=sub,
                scheduled_delivery_date=target_date,
                status=OrderStatus.PENDING, # Starts as PENDING for admin review
                delivery_address=sub.delivery_address or sub.customer.address,
                delivery_notes=sub.special_instructions
            )
            
            total_amount = 0
            for item in sub.items.all():
                OrderItem.objects.create(
                    order=order,
                    product=item.product,
                    quantity=item.quantity,
                    unit_price=item.product.unit_price
                )
                total_amount += (item.product.unit_price * item.quantity)
                
            order.total = total_amount
            order.save(update_fields=['total'])
            
            generated_count += 1
            
    return {
        'status': 'success',
        'generated': generated_count,
        'skipped': skipped_count
    }
