import datetime
import logging
from celery import shared_task
from django_tenants.utils import schema_context

from tenants.models import City
from orders.services.route_generator import generate_daily_routes_for_date
from orders.services.trip_management import (
    process_pre_delivery_product_cutoff,
    auto_stop_active_trips_at_noon
)

logger = logging.getLogger(__name__)


@shared_task(name="orders.tasks.generate_next_day_routes")
def generate_next_day_routes_task(target_date_str=None):
    """
    Celery task that executes daily at 12:00 AM (midnight) to automatically generate
    and optimize routes for the NEXT DAY across all active cities (tenants).
    """
    if target_date_str:
        target_date = datetime.date.fromisoformat(target_date_str)
    else:
        target_date = datetime.date.today() + datetime.timedelta(days=1)

    logger.info("Executing Celery Task: generate_next_day_routes for date: %s", target_date)
    
    cities = City.objects.exclude(schema_name='public')
    results = {}

    for city in cities:
        logger.info("Running automatic route generation for City schema: %s", city.schema_name)
        with schema_context(city.schema_name):
            try:
                stats = generate_daily_routes_for_date(target_date)
                results[city.schema_name] = stats
            except Exception as e:
                logger.exception("Failed to generate routes for City schema %s", city.schema_name)
                results[city.schema_name] = {"status": "failed", "error": str(e)}

    return results


@shared_task(name="orders.tasks.auto_lock_routes_at_6am")
def auto_lock_routes_at_6am_task():
    """
    Celery task that executes daily at 6:00 AM for the daily cutoff.
    (Previously locked all routes; now just runs process_pre_delivery_product_cutoff logging).
    """
    logger.info("Executing Celery Task: auto_lock_routes_at_6am")
    
    cities = City.objects.exclude(schema_name='public')
    results = {}

    for city in cities:
        logger.info("Running pre-delivery product cutoff check for City schema: %s", city.schema_name)
        with schema_context(city.schema_name):
            try:
                stats = process_pre_delivery_product_cutoff()
                results[city.schema_name] = stats
            except Exception as e:
                logger.exception("Failed pre-delivery cutoff check for City schema %s", city.schema_name)
                results[city.schema_name] = {"status": "failed", "error": str(e)}

    return results


@shared_task(name="orders.tasks.auto_stop_trips_at_12pm")
def auto_stop_trips_at_12pm_task():
    """
    Celery task that executes daily at 12:00 PM (noon) to automatically complete/stop
    any remaining active trips today and mark pending orders as undelivered.
    """
    logger.info("Executing Celery Task: auto_stop_trips_at_12pm")
    
    cities = City.objects.exclude(schema_name='public')
    results = {}

    for city in cities:
        logger.info("Running automatic trip stop for City schema: %s", city.schema_name)
        with schema_context(city.schema_name):
            try:
                stats = auto_stop_active_trips_at_noon()
                results[city.schema_name] = stats
            except Exception as e:
                logger.exception("Failed to auto stop trips for City schema %s", city.schema_name)
                results[city.schema_name] = {"status": "failed", "error": str(e)}

    return results
